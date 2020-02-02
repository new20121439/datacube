from django.shortcuts import render
from .models import User, Job

# Create your views here.
def index(request):
    user_obj = User.objects.all()
    # job_obj = Job.objects.get(job_id=user_obj)
    context = {'task': user_obj}
    return render(request, 'index.html', context)