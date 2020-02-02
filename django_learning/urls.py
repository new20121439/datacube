from django.conf.urls import url
from . import views

urlpatterns = [
    url('', name='index', view=views.index),
]