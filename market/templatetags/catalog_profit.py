"""Small read-only links into the existing profit workspace."""
from django import template
from market.catalog_profit_references import catalog_profit_link, candidate_profit_link
register = template.Library()
register.simple_tag(catalog_profit_link, name='catalog_profit_link')
register.simple_tag(candidate_profit_link, name='candidate_profit_link')
