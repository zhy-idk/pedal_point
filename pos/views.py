from django.shortcuts import render

# Create your views here.
def pos(request):
    return render(request, 'pos/pos.html')