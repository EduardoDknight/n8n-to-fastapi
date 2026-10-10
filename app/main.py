import hashlib
import logging
import time

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import ValidationError

from .classifier import Classifier, build_classifier
from .config import Settings
from .enrich import enrich
from .logging_setup import log, setup_logging
from .models import Lead, LeadResult
from .retry import with_retry
from .security import verify_signature
from .sinks import ROUTES, Sink, build_sink
from .store import Store

logger = logging.getLogger("app")


def create_app(
    settings: Settings | None = None,
    classifier: Classifier | None = None,
    sink: Sink | None = None,
    retry_base_delay: float = 0.2,
) -> FastAPI:
    settings = settings or Settings()
    setup_logging(settings.log_level)
    app = FastAPI(title="Lead Router", version="1.0.0")
    app.state.store = Store(settings.db_path)
    app.state.classifier = classifier or build_classifier(settings.anthropic_api_key, settings.anthropic_model)
    app.state.sink = sink or build_sink(settings.sinks)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "classifier": type(app.state.classifier).__name__}

    @app.post("/webhook/lead", response_model=LeadResult)
    async def webhook_lead(
        request: Request,
        x_signature: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> LeadResult:
        started = time.perf_counter()
        body = await request.body()
        if not verify_signature(body, x_signature, settings.webhook_secret):
            raise HTTPException(status_code=401, detail="invalid signature")
        try:
            lead = Lead.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_input=False)) from None

        # No explicit key: dedupe on the body hash (form providers often resend the same payload).
        key = idempotency_key or hashlib.sha256(body).hexdigest()
        store: Store = app.state.store
        existing = store.claim(key)
        if existing is not None:
            if existing["status"] != "done":
                raise HTTPException(status_code=409, detail="request with this key is in progress")
            log(logger, "duplicate ignored", key=key)
            return LeadResult(**{**existing["result"], "duplicate": True})

        try:
            enriched = enrich(lead)
            c = await app.state.classifier.classify(enriched)
            destinations = ROUTES[c.tier]
            for dest in destinations:
                await with_retry(lambda d=dest: app.state.sink.send(d, enriched, c), base_delay=retry_base_delay)
                store.audit(key, f"sent:{dest}")
        except Exception:
            store.audit(key, "failed")
            store.release(key)
            logger.exception("lead processing failed")
            raise HTTPException(status_code=502, detail="downstream delivery failed") from None

        result = LeadResult(lead_id=key[:16], tier=c.tier, classifier=c.source, routed_to=destinations)
        store.complete(key, result.model_dump())
        log(logger, "lead processed", key=key, tier=c.tier, classifier=c.source, routed_to=destinations,
            ms=round((time.perf_counter() - started) * 1000, 1))
        return result

    return app


app = create_app()
