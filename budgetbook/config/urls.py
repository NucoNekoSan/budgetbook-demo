from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL_PATH, admin.site.urls),
    path('accounts/login/', LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True,
    ), name='login'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    path('', include('ledger.urls')),
]