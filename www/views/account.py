# -*- coding: utf8 -*-
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.template.response import TemplateResponse
from django.http import JsonResponse
from django.http import HttpResponse, Http404

from www.auth import authenticate, login, logout
from www.forms.account import UserLoginForm, RegisterForm, PasswordResetForm, PasswordResetBeginForm
from www.models import Users, Tenants, TenantRegionInfo, TenantServiceInfo, AnonymousUser, PermRelTenant, PermRelService, PhoneCode, TenantRecharge
from www.utils.crypt import AuthCode
from www.utils.mail import send_reset_pass_mail
from www.sms_service import send_phone_message
from www.db import BaseConnection
import datetime
import time
import random
import re

from www.region import RegionInfo
from www.views import BaseView, RegionOperateMixin
from www.monitorservice.monitorhook import MonitorHook
from www.tenantservice.baseservice import CodeRepositoriesService

import hashlib

import logging
logger = logging.getLogger('default')

codeRepositoriesService = CodeRepositoriesService()

monitorhook = MonitorHook()



class Login(BaseView):

    def get_context(self):
        context = super(Login, self).get_context()
        context.update({
            'form': self.form,
        })
        return context

    def get_media(self):
        media = super(Login, self).get_media(
        ) + self.vendor('www/css/goodrainstyle.css', 'www/js/jquery.cookie.js')
        return media

    def get_response(self):
        return TemplateResponse(self.request, 'www/account/login.html', self.get_context())

    def redirect_view(self):
        tenants_has = PermRelTenant.objects.filter(user_id=self.user.pk)
        if tenants_has:
            tenant_pk = tenants_has[0].tenant_id
            tenant = Tenants.objects.get(pk=tenant_pk)
            tenant_name = tenant.tenant_name
            return self.redirect_to('/apps/{0}/'.format(tenant_name))
        else:
            logger.error('account.login_error', 'user {0} with id {1} has no tenants to redirect login'.format(
                self.user.nick_name, self.user.pk))
            return Http404

    def get(self, request, *args, **kwargs):
        user = request.user
        if isinstance(user, AnonymousUser):
            self.form = UserLoginForm()
            return self.get_response()
        else:
            # 判断是否有跳转参数,有参数跳转到返回页面
            next_url = request.GET.get('next', None)
            if next_url is not None:
                # next_url += '?nick_name={}&email={}'.format(user.nick_name, user.email)
                return self.redirect_to(next_url)
            return self.redirect_view()

    @never_cache
    def post(self, request, *args, **kwargs):
        self.form = UserLoginForm(request.POST)
        next_url = request.GET.get('next', None)
        username = request.POST.get('email')
        password = request.POST.get('password')

        if not self.form.is_valid():
            logger.info('account.login_error', "login form is not right: %s" % self.form.errors)
            return self.get_response()
        user = authenticate(username=username, password=password)
        login(request, user)
        logger.info('account.login', "user {0} success login in".format(user.nick_name))

        # create git user
        codeRepositoriesService.createUser(user, username, password, user.nick_name, user.nick_name)
        
        # to judge from www create servcie
        app_ty = request.COOKIES.get('app_ty')
        if app_ty is not None:
            return self.redirect_to("/autodeploy?fr=www_app")

        if next_url is not None:
            next_url += '?nick_name={}&email={}'.format(user.nick_name, user.email)
            return self.redirect_to(next_url)
        else:
            return self.redirect_view()


class Index(Login):

    def get(self, request, *args, **kwargs):
        user = request.user
        if isinstance(user, AnonymousUser):
            return self.redirect_to('/login')
        else:
            return self.redirect_view()

    def post(self, request, *args, **kwargs):
        return HttpResponse("POST METHOD IS NOT ALLOWED")


class Logout(BaseView):

    def init_request(self, *args, **kwargs):
        self.template = 'www/logout.html'

    def get_context(self):
        context = super(Logout, self).get_context()
        context.update({
            'form': self.form,
        })
        return context

    def get_media(self):
        media = super(Logout, self).get_media()
        return media

    def get_response(self):
        return TemplateResponse(self.request, self.template, self.get_context())

    def get(self, request, *args, **kwargs):
        user = request.user
        if isinstance(user, AnonymousUser):
            return HttpResponse("未登录状态, 不需注销")
        else:
            logout(request)
            logger.info('account.login', 'user {0} logout'.format(user.nick_name))
            return self.redirect_to(settings.LOGIN_URL)

    @never_cache
    def post(self, request, *args, **kwargs):
        logout(request)
        return self.redirect_to(settings.LOGIN_URL)


class PasswordResetBegin(BaseView):

    def get_context(self):
        context = super(PasswordResetBegin, self).get_context()
        context.update({
            'form': self.form,
            'title': u'账号确认',
        })
        return context

    def get_media(self):
        media = super(PasswordResetBegin, self).get_media()
        return media

    def get_response(self):
        return TemplateResponse(self.request, 'www/account/reset_password.html', self.get_context())

    def get(self, request, *args, **kwargs):
        self.form = PasswordResetBeginForm()
        return self.get_response()

    def post(self, request, *args, **kwargs):
        self.form = PasswordResetBeginForm(request.POST)
        if self.form.is_valid():
            account = request.POST.get('account')
            logger.info('account.passwdreset', "account {0} apply for reset password".format(account))
            tag = '{0}:{1}'.format(int(time.time()), account)
            return self.redirect_to('/account/select_verify_method?tag=%s' % AuthCode.encode(tag, 'reset_password'))
        return self.get_response()


class PasswordResetMethodSelect(BaseView):

    def get_context(self):
        context = super(PasswordResetMethodSelect, self).get_context()
        context.update({
            'title': u'验证方式',
            'account': self.account,
            'methods': [
                {"value": "email", "desc": "密保邮箱 <%s>" % self.user.safe_email},
                # {"value": "phone", "desc": self.user.phone},
            ],
        })
        return context

    def get_media(self):
        media = super(PasswordResetMethodSelect, self).get_media()
        return media

    def get_response(self):
        return TemplateResponse(self.request, 'www/account/select_verify_method.html', self.get_context())

    def get_user_instance(self, account):
        try:
            if '@' in account:
                user = Users.objects.get(email=account)
            else:
                user = Users.objects.get(phone=account)
            self.user = user
            return user
        except user.DoesNotExist:
            return None

    def get(self, request, *args, **kwargs):
        tag = str(request.GET.get('tag'))
        old_timestamp, account = AuthCode.decode(tag, 'reset_password').split(':')
        timestamp = int(time.time())
        if (timestamp - int(old_timestamp)) > 60:
            return HttpResponse("过期的URL, 请重新开始")

        self.account = account
        self.user = self.get_user_instance(account)
        if self.user is None:
            return HttpResponse(u"账号不存在")
        return self.get_response()

    def post(self, request, *args, **kwargs):
        tag = str(request.GET.get('tag'))
        old_timestamp, account = AuthCode.decode(tag, 'reset_password').split(':')
        verify_method = request.POST.get('verify_method')
        self.user = self.get_user_instance(account)
        self.account = account

        if verify_method == 'email':
            domain = self.request.META.get('HTTP_HOST')
            timestamp = str(int(time.time()))
            tag = AuthCode.encode(','.join([self.user.email, timestamp]), 'password')
            link_url = 'https://{0}/account/reset_password?tag={1}'.format(domain, tag)
            try:
                send_reset_pass_mail(self.user.email, link_url)
            except Exception, e:
                logger.error("account.passwdreset", "send email to {0} failed".format(self.user.email))
                logger.exception("account.passwdreset", e)
            mail_address = 'http://mail.' + self.user.email.split('@')[1]
            return TemplateResponse(self.request, 'www/account/email_sended.html', {"safe_email": self.user.safe_email, "mail_address": mail_address})
        return self.get_response()


class PasswordReset(BaseView):

    def get_context(self):
        context = super(PasswordReset, self).get_context()
        context.update({
            'form': self.form,
            'title': u'重置密码',
        })
        return context

    def get_media(self):
        media = super(PasswordReset, self).get_media()
        return media

    def get_response(self):
        return TemplateResponse(self.request, 'www/account/reset_password.html', self.get_context())

    def get_user_instance(self, account):
        try:
            if '@' in account:
                user = Users.objects.get(email=account)
            else:
                user = Users.objects.get(phone=account)
            self.user = user
            return user
        except user.DoesNotExist:
            return None

    def create_git_user(self, user, password):
        logger.info("account.passwdreset", "user {0} didn't owned a gitlab user_id, will create it".format(user.nick_name))
        codeRepositoriesService.createUser(user, user.email, password, user.nick_name, user.nick_name)
        

    def get(self, request, *args, **kwargs):
        self.form = PasswordResetForm()
        return self.get_response()

    def post(self, request, *args, **kwargs):
        tag = str(request.GET.get('tag'))
        email, old_timestamp = AuthCode.decode(tag, 'password').split(',')
        timestamp = int(time.time())
        if (timestamp - int(old_timestamp)) > 3600:
            logger.info("account.passwdreset", "link expired, email: {0}, link_timestamp: {1}".format(email, old_timestamp))
            return HttpResponse(u"处理已过期, 请重新开始")

        user = self.get_user_instance(email)
        self.form = PasswordResetForm(request.POST)
        if self.form.is_valid():
            raw_password = request.POST.get('password')
            user.set_password(raw_password)
            user.save()
            flag = True
            logger.info("account.passwdreset", "reset password for user {0} in my database".format(user.nick_name))
            if user.git_user_id != 0:
                try:
                    codeRepositoriesService.modifyUser(user, raw_password)
                    logger.info("account.passwdreset", "reset password for user {0} in gitlab".format(user.nick_name))
                except Exception, e:
                    logger.error("account.passwdreset", "reset password for user {0} in gitlab failed".format(user.nick_name))
                    logger.exception("account.passwdreset", e)
                    flag = False
            else:
                self.create_git_user(user, raw_password)
            monitorhook.passwdResetMonitor(user, flag)
            return self.redirect_to('/login')
        logger.info("account.passwdreset", "passwdreset form error: %s" % self.form.errors)
        return self.get_response()


class Registation(BaseView, RegionOperateMixin):

    def get_context(self):
        context = super(Registation, self).get_context()
        context.update({
            'form': self.form,
        })
        return context

    def get_media(self):
        media = super(Registation, self).get_media(
        ) + self.vendor('www/css/goodrainstyle.css', 'www/js/jquery.cookie.js', 'www/js/validator.min.js')
        return media

    def get_response(self):
        return TemplateResponse(self.request, 'www/account/register.html', self.get_context())

    def get(self, request, *args, **kwargs):
        pl = request.GET.get("pl", "")
        region_levels = pl.split(":")
        if len(region_levels) == 2:
            region = region_levels[0]
            self.form = RegisterForm(
                region_level={
                    "region": region,
                }
            )
        else:
            self.form = RegisterForm()
        return self.get_response()

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def weixinRegister(self, tenant_id, user_id, user_name, rf):
        try:
            sendRecharge = TenantRecharge()
            sendRecharge.tenant_id = tenant_id
            sendRecharge.user_id = user_id
            sendRecharge.user_name = user_name
            sendRecharge.order_no = str(user_id)
            sendRecharge.recharge_type = "weixin100"
            sendRecharge.money = 100
            sendRecharge.subject = "免费送"
            sendRecharge.body = "注册送100"
            sendRecharge.show_url = ""
            sendRecharge.time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sendRecharge.status = "TRADE_SUCCESS"
            sendRecharge.save()
            tenant = Tenants.objects.get(tenant_id=tenant_id)
            tenant.balance = tenant.balance + 100
            tenant.save()
        except Exception as e:
            logger.exception(e)

    def post(self, request, *args, **kwargs):
        querydict = request.POST
        querydict.update(
            {u'real_captcha_code': request.session.get("captcha_code")})
        self.form = RegisterForm(querydict)
        if self.form.is_valid():
            rf = request.GET.get("rf", "")
            email = request.POST.get('email')
            nick_name = request.POST.get('nick_name')
            password = request.POST.get('password')
            tenant_name = request.POST.get('tenant')
            phone = request.POST.get('phone')
            region = request.POST.get('machine_region')
            if region is None or region == "" or region == "1":
                region = "ucloud_bj_1"
            user = Users(email=email, nick_name=nick_name,
                         phone=phone, client_ip=self.get_client_ip(request), rf=rf)
            user.set_password(password)
            user.save()
            monitorhook.registerMonitor(user, 'register')

            tenant = Tenants.objects.create(
                tenant_name=tenant_name, pay_type='free', creater=user.pk, region=region)

            monitorhook.tenantMonitor(tenant, user, "create_tenant", True)

            PermRelTenant.objects.create(
                user_id=user.pk, tenant_id=tenant.pk, identity='admin')
            logger.info(
                "account.register", "new registation, nick_name: {0}, tenant: {1}, region: {2}, tenant_id: {3}".format(nick_name, tenant_name, region, tenant.tenant_id))

            TenantRegionInfo.objects.create(tenant_id=tenant.tenant_id, region_name=tenant.region)
            init_result = self.init_for_region(tenant.region, tenant_name, tenant.tenant_id)
            monitorhook.tenantMonitor(tenant, user, "init_tenant", init_result)
            # create gitlab user
            codeRepositoriesService.createUser(user, email, password, nick_name, nick_name)

            # wei xin user need to add 100
            if rf == "wx":
                self.weixinRegister(tenant.tenant_id, user.pk, user.nick_name, rf)

            user = authenticate(username=email, password=password)
            login(request, user)

            # to judge from www create servcie
            app_ty = request.COOKIES.get('app_ty')
            if app_ty is not None:
                return self.redirect_to("/autodeploy?fr=www_app")
            
            url = '/apps/{0}'.format(tenant_name)
            if settings.MODULES["Package_Show"]:
                selected_pay_level = ""
                pl = request.GET.get("pl", "")
                region_levels = pl.split(":")
                if len(region_levels) == 2:
                    selected_pay_level = region_levels[1]
                url = '/payed/{0}/select?selected={1}'.format(tenant_name, selected_pay_level)
            logger.debug(url)
            return self.redirect_to(url)

        logger.info("account.register", "register form error: %s" % self.form.errors)
        return self.get_response()


class InviteRegistation(BaseView):

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def get_context(self):
        context = super(InviteRegistation, self).get_context()
        context.update({
            'form': self.form,
        })
        return context

    def get_media(self):
        media = super(InviteRegistation, self).get_media(
        ) + self.vendor('www/css/goodrainstyle.css', 'www/js/jquery.cookie.js')
        return media

    def get_response(self):
        return TemplateResponse(self.request, 'www/account/register.html', self.get_context())

    def register_for_tenant(self, user, password, data):
        email, tenant_name, identity = data
        tenant = Tenants.objects.get(tenant_name=tenant_name)
        PermRelTenant.objects.create(
            user_id=user.pk, tenant_id=tenant.pk, identity=identity)
        self.add_git_user(user, password)

    def register_for_service(self, user, password, data):
        email, tenant_name, service_alias, identity = data
        tenant = Tenants.objects.get(tenant_name=tenant_name)
        service = TenantServiceInfo.objects.get(
            tenant_id=tenant.tenant_id, service_alias=service_alias)
        PermRelService.objects.create(
            user_id=user.pk, service_id=service.pk, identity=identity)

        perm_t, created = PermRelTenant.objects.get_or_create(
            user_id=user.pk, tenant_id=tenant.pk)
        if created:
            perm_t.identity = 'access'
            perm_t.save()
            self.add_git_user(user, password)

        git_project_id = service.git_project_id
        if service.code_from != 'github' and git_project_id > 0 and user.git_user_id > 0:
            level = 10
            if identity == "viewer":
                level = 20
            elif identity == "developer":
                level = 30
            elif identity == "admin":
                level = 40
            codeRepositoriesService.addProjectMember(git_project_id, user.git_user_id, level)

    def add_git_user(self, user, password):
        codeRepositoriesService.createUser(user, user.email, password, user.nick_name, user.nick_name)

    def get(self, request, *args, **kwargs):
        encoded_data = str(request.GET.get('key'))
        self.key = encoded_data
        logger.debug(self.key)
        data = AuthCode.decode(encoded_data, 'goodrain').split(',')
        logger.debug(data)
        # tenant member
        if len(data) == 3:
            self.email, self.tenant_name = data[0:2]
            self.service_name = ""
        elif len(data) == 4:
            self.email, self.tenant_name, self.service_name = data[0:3]
        else:
            self.redirect_to('/register')

        try:
            if self.email.find("@") > 0:
                Users.objects.get(email=self.email)
            else:
                Users.objects.get(phone=self.email)
            return self.redirect_to('/login')
        except Users.DoesNotExist:
            curemail = ""
            curphone = ""
            if self.email.find("@"):
                curemail = self.email
            else:
                curphone = self.email
            registerTenant = Tenants.objects.get(tenant_name=self.tenant_name)
            self.form = RegisterForm(
                initial={
                    "tenant": self.tenant_name,
                    "phone": curphone,
                    "email": curemail,
                    "region": registerTenant.region
                }
            )
            return self.get_response()

    def post(self, request, *args, **kwargs):
        encoded_data = str(request.GET.get('key'))
        data = AuthCode.decode(encoded_data, 'goodrain').split(',')
        querydict = request.POST
        querydict.update({u'invite_tag': "invite"})
        querydict.update(
            {u'real_captcha_code': request.session.get("captcha_code")})
        self.form = RegisterForm(querydict)
        if not self.form.is_valid():
            initial = {"tenant": request.POST.get('tenant'), "phone": request.POST.get(
                'phone'), "email": request.POST.get('email'), "region": request.POST.get('machine_region')}
            querydict.update({"initial": initial})
            self.form = RegisterForm(querydict)
            return self.get_response()

        email = request.POST.get('email')
        nick_name = request.POST.get('nick_name')
        password = request.POST.get('password')
        tenant_name = request.POST.get('tenant')
        phone = request.POST.get('phone')
        user = Users(email=email, nick_name=nick_name,
                     phone=phone, client_ip=self.get_client_ip(request))
        user.set_password(password)
        user.save()
        monitorhook.registerMonitor(user, "invite_register")

        if len(data) == 3:
            self.register_for_tenant(user, password, data)
        elif len(data) == 4:
            self.register_for_service(user, password, data)
        else:
            self.register_for_service(user, password, data)
        user = authenticate(username=email, password=password)
        login(request, user)
        return self.redirect_to('/apps/{0}'.format(tenant_name))


class PhoneCodeView(BaseView):

    def post(self, request, *args, **kwargs):
        result = {}
        phone = request.POST.get('phone')
        captcha_code = request.POST.get('captcha_code')
        real_captcha_code = request.session.get("captcha_code")
        logger.debug(captcha_code)
        logger.debug(real_captcha_code)
        if captcha_code.lower() != real_captcha_code.lower():
            result["status"] = "errorcaptchacode"
            return JsonResponse(result)

        if phone is not None:
            r = re.compile(r'^1[3578]\d{9}$|^147\d{8}$')
            if not r.match(phone):
                result["status"] = "errorphone"
                return JsonResponse(result)
        else:
            result["status"] = "errorphone"
            return JsonResponse(result)
        try:
            phoneCodes = PhoneCode.objects.filter(
                phone=phone).order_by('-ID')[:1]
            if len(phoneCodes) > 0:
                phoneCode = phoneCodes[0]
                last = int(phoneCode.create_time.strftime("%s"))
                now = int(time.time())
                if now - last < 90:
                    result["status"] = "often"
                    return JsonResponse(result)
            dsn = BaseConnection()
            query_time = datetime.datetime.now().strftime('%Y-%m-%d')
            query_sql = '''
                select count(1) as sendNumber from phone_code where phone = "{phone}" and create_time >= "{query_time}"
                '''.format(phone=phone, query_time=query_time + " 00:00:00")
            sqlobj = dsn.query(query_sql)
            if len(sqlobj) > 0:
                sendNumber = int(sqlobj[0]["sendNumber"])
                if sendNumber > 3:
                    result["status"] = "limited"
                    return JsonResponse(result)
            phone_code = random.randrange(0, 1000001, 6)
            send_result = send_phone_message(phone, phone_code)
            if not send_result:
                send_result = send_phone_message(phone, phone_code)
            newpc = PhoneCode(phone=phone, type="register", code=phone_code)
            newpc.save()
            monitorhook.phoneCodeMonitor(phone, phone_code, send_result)
            result["status"] = "success"
            return JsonResponse(result)
        except Exception as e:
            logger.exception(e)
        result["status"] = "error"
        return JsonResponse(result)


class TenantSelectView(BaseView):

    def get_tenant_names(self):
        tids = PermRelTenant.objects.filter(user_id=self.user.pk).values_list("tenant_id", flat=True)
        tnames = Tenants.objects.filter(pk__in=tids).values_list("tenant_name", flat=True)
        return tnames

    def get(self, request, *args, **kwargs):
        if isinstance(self.user, AnonymousUser):
            return self.redirect_to('/login')

        tenant_names = self.get_tenant_names()
        # tenant_names = ['testa', 'testb']
        regions = RegionInfo.register_choices()
        context = self.get_context()
        context.update({"tenant_names": tenant_names, "regions": regions})

        return TemplateResponse(request, 'www/account/select_tenant.html', context)

    def post(self, request, *args, **kwargs):
        post_data = request.POST.dict()
        get_paras = request.GET.dict()
        action = get_paras.pop("action", None)
        tenant = post_data.get('tenant')
        region = post_data.get('region')

        if action is None:
            return self.get(request, *args, **kwargs)
        elif action == 'app_install':
            service_key = get_paras.get('service_key')
            next_url = '/apps/{0}/service-deploy/?service_key={2}&region={1}'.format(tenant, region, service_key)
            return self.redirect_to(next_url)


class AccountView(BaseView):
    """用户信息视图"""
    def post(self, request, *args, **kwargs):
        email = request.POST.get('email', None)
        if email is None:
            return JsonResponse({"success": False, "nick_name": "Anonymous"})
        user_info = Users.objects.get(email=email)
        if user_info is None:
            return JsonResponse({"success": False, "nick_name": "Anonymous"})
        else:
            return JsonResponse({"success": True, "nick_name": user_info.nick_name})
