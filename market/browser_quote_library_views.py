"""One login-required GET list, with 20 rows and a deterministic order."""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .browser_quote_library import owned_quotes, filtered_quotes
from .browser_quote_library_forms import BrowserQuoteLibraryForm


@login_required
@require_GET
def library(request):
    form = BrowserQuoteLibraryForm(request.GET, owner=request.user)
    valid = form.is_valid()
    filters = form.cleaned_data if valid else {}
    rows = filtered_quotes(request.user, filters) if valid else owned_quotes(request.user).none()
    page = Paginator(rows, 20).get_page(request.GET.get('page', '')[:20])
    from urllib.parse import urlencode
    query = urlencode({name: filters[name] for name in ('q', 'platform', 'currency') if filters.get(name)})
    return render(request, 'market/browser_quote_library.html', {
        'form': form, 'page': page, 'filter_query': query,
        'has_quotes': owned_quotes(request.user).exists(), 'has_filters': bool(query),
    })
