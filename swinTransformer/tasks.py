from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


@shared_task(bind=True, max_retries=3)
def send_custom_email(self, subject, template_name, context, recipient_list):
    """
    :param self:
    :param subject: 邮件主题
    :param template_name: 邮件模板名称
    :param context: 邮件模板上下文
    :param recipient_list: 收件人列表
    """
    try:
        message = render_to_string(template_name, context)
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=False
        )
    except Exception as e:
        self.retry(exc=e, countdown=60)
