# Generated by Django 3.2.15 on 2025-01-13 03:57

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('swinTransformer', '0002_auto_20241223_1752'),
    ]

    operations = [
        migrations.RenameField(
            model_name='segmentedimage',
            old_name='segmented_image_path',
            new_name='image_path',
        ),
    ]
