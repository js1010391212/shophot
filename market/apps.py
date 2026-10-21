from django.apps import AppConfig


class MarketConfig(AppConfig):
    name = 'market'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from django.contrib.auth import get_user_model
        from django.db.models.signals import pre_save
        from .admin_account_policy import protect_new_privileged_account

        pre_save.connect(protect_new_privileged_account, sender=get_user_model(),
                         dispatch_uid='shophot.new_privileged_account', weak=False)
