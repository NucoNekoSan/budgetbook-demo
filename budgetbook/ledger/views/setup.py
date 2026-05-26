from __future__ import annotations

from django.contrib.auth import get_user_model, login
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..forms import FirstRunSetupForm


@require_http_methods(['GET', 'POST'])
def first_run_setup(request: HttpRequest) -> HttpResponse:
    User = get_user_model()
    if User.objects.exists():
        return redirect('ledger:dashboard')

    if request.method == 'POST':
        form = FirstRunSetupForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    if User.objects.exists():
                        return redirect('ledger:dashboard')
                    user = form.save()
                    if form.cleaned_data.get('create_default_masters'):
                        call_command('seed_default_master_data', verbosity=0)
            except IntegrityError:
                return redirect('ledger:dashboard')
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('ledger:dashboard')
    else:
        form = FirstRunSetupForm()

    return render(request, 'registration/setup.html', {'form': form})