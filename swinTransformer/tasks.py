from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


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
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)
        email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, recipient_list)
        email.attach_alternative(html_content, 'text/html')
        email.send()
    except Exception as e:
        self.retry(exc=e, countdown=60)
