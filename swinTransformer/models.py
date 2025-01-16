from django.db import models


# Create your models here.

class User(models.Model):
    username = models.CharField(max_length=32, unique=False)
    password = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # example: what_103
    def __str__(self):
        return f'{self.username}_{self.id}'


class OriginalImage(models.Model):
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='original_images'
    )
    image_path = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'OriginalImage {self.id} for user {self.user.username}'


class SegmentedImage(models.Model):
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='segmented_images'
    )
    original_image = models.ForeignKey(
        'OriginalImage',
        on_delete=models.CASCADE,
        related_name='segmented_images'
    )
    image_path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'segmented_images'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['original_image'])
        ]
    def __str__(self):
        return f'SegmentedImage {self.id} for user {self.user.username}'

