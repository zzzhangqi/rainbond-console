from django.http import HttpResponse
from base import BaseView, AuthedView
from account import *

__all__ = ('BaseView', 'AuthedView')


def monitor(request):
    return HttpResponse("ok")


def ssl_crv(request):
    return HttpResponse("Ea7e1ps5")
