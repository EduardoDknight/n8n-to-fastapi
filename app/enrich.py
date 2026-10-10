from .models import EnrichedLead, Lead

FREE_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}


def enrich(lead: Lead) -> EnrichedLead:
    """Offline stand-in for the n8n 'Company Lookup' HTTP node. Swap for a real provider adapter."""
    domain = lead.email.split("@", 1)[1].lower()
    if domain in FREE_MAIL:
        size = "individual"
    elif (lead.budget or 0) >= 20000:
        size = "mid-market"
    else:
        size = "smb"
    return EnrichedLead(**lead.model_dump(), domain=domain, company_size=size)
