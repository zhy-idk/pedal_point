from django.shortcuts import render

# Create your views here.
def service_queue(request):
    return render(request, 'service_queue/service_queue.html')