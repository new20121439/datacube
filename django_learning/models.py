from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

# Create your models here.
class User(models.Model):
    user_name = models.CharField(max_length=100, default="")
    age = models.IntegerField(default=1, validators=[MaxValueValidator(200), MinValueValidator(1)])

class Job(models.Model):
    job_id = models.ForeignKey(User, on_delete=models.CASCADE)
    job = models.CharField(max_length=100, default="")
    work_place = models.CharField(max_length=200, default="")
