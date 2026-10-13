"""Read-only first-use guidance: no business queries or queued work."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET


@login_required
@require_GET
def guide(request):
    return render(request, 'market/first_use.html')
