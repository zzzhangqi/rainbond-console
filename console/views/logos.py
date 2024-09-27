# -*- coding: utf8 -*-
import json
import logging
import os
from datetime import datetime

from django.db import transaction
from rest_framework.response import Response

from console.exception.main import ServiceHandleException
from console.models.main import ConsoleSysConfig
from console.repositories.perm_repo import perms_repo
from console.repositories.team_repo import team_repo
from console.services.config_service import (EnterpriseConfigService, platform_config_service)
from console.services.perm_services import role_kind_services
from console.services.perm_services import user_kind_role_service
from console.views.base import AlowAnyApiView
from console.views.base import BaseApiView
from console.views.jwt_token_view import JWTTokenView
from www.models.main import Tenants, Users
from www.utils.return_message import error_message
from www.utils.return_message import general_message

logger = logging.getLogger("default")


class ConfigOSSView(JWTTokenView):

    def get(self, request, *args, **kwargs):
        oss_config = ConsoleSysConfig.objects.filter(key='OSS_CONFIG').first()
        if oss_config:
            data = json.loads(oss_config.value)
            return Response(data=data, status=200)
        return Response(data={}, status=200)

    def put(self, request, *args, **kwargs):
        oss_config = ConsoleSysConfig.objects.filter(key='OSS_CONFIG').first()

        # 如果已存在，则更新；如果不存在，则创建
        if oss_config:
            oss_config.value = json.dumps(request.data)
            oss_config.desc = 'OSS 配置'
            oss_config.create_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            oss_config.save()
            data = {'message': '配置更新成功'}
        else:
            new_config = ConsoleSysConfig.objects.create(
                key='OSS_CONFIG',
                type='json',
                value=json.dumps(request.data),
                desc='OSS 配置',
                create_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                enterprise_id=""
            )
            data = {'message': '配置创建成功', 'config_id': new_config.ID}

        return Response(data=data, status=200)


class ConfigRUDView(AlowAnyApiView):
    """
    获取配置信息
    ---
    """

    def get(self, request, *args, **kwargs):
        code = 200
        user = request.user
        status = perms_repo.initialize_permission_settings()
        data = platform_config_service.initialization_or_get_config
        if data.get("enterprise_id", None) is None:
            data["enterprise_id"] = os.getenv('ENTERPRISE_ID', '')
        shadow_value = data["shadow"]["value"]
        if shadow_value:
            value = True if shadow_value.lower() == 'true' else False
            shadow = {"enable": value, "value": value}
            data["shadow"] = shadow
        if isinstance(user, Users):
            data["enterprise_id"] = user.enterprise_id
            ent_config = EnterpriseConfigService(data["enterprise_id"]).initialization_or_get_config
            data["title"] = ent_config["title"]
            data["logo"] = ent_config["logo"]
            data["favicon"] = ent_config["favicon"]
            data["document"] = ent_config["document"]
            data["header_color"] = ent_config["header_color"]
            data["header_writing_color"] = ent_config["header_writing_color"]
            data["sidebar_color"] = ent_config["sidebar_color"]
            data["sidebar_writing_color"] = ent_config["sidebar_writing_color"]
            data["footer"] = ent_config["footer"]
            data["login_image"] = ent_config["login_image"]
            data["official_demo"] = ent_config["official_demo"]
            data["captcha_code"] = ent_config["captcha_code"]
        data["is_disable_logout"] = os.getenv('IS_DISABLE_LOGOUT', False)
        data["is_offline"] = os.getenv('IS_OFFLINE', False)
        data["sso_enable"] = os.getenv("SSO_ENABLE", False)
        data['diy'] = False if os.getenv('DIY', 'True').lower() == 'false' else True
        data["enable_yum_oauth"] = True if os.getenv("ENABLE_YUM_OAUTH") else False
        data["diy_customer"] = os.getenv("DIY_CUSTOMER", 'rainbond')
        data["is_delivery_version"] = True if os.getenv("IS_DELIVERY_VERSION") else False
        result = general_message(code, "query success", "Logo获取成功", bean=data, initialize_info=status)
        return Response(result, status=code)

    def put(self, request, *args, **kwargs):
        key = request.GET.get("key")
        if not key:
            result = general_message(404, "no found config key", "更新失败")
            return Response(result, status=result.get("code", 200))
        value = request.data.get(key, None)
        if not value:
            result = general_message(404, "no found config value", "更新失败")
            return Response(result, status=result.get("code", 200))
        key = key.upper()
        if key in platform_config_service.base_cfg_keys + platform_config_service.cfg_keys:
            data = platform_config_service.update_config(key, value)
            try:
                result = general_message(200, "success", "更新成功", bean=data)
            except Exception as e:
                logger.debug(e)
                raise ServiceHandleException(msg="update enterprise config failed", msg_show="更新失败")
        else:
            result = general_message(404, "no found config key", "更新失败")
        return Response(result, status=result.get("code", 200))

    def delete(self, request, *args, **kwargs):
        key = request.GET.get("key")
        if not key:
            result = general_message(404, "no found config key", "重置失败")
            return Response(result, status=result.get("code", 200))
        value = request.data.get(key)
        if not value:
            result = general_message(404, "no found config value", "重置失败")
            return Response(result, status=result.get("code", 200))
        key = key.upper()
        if key in platform_config_service.cfg_keys:
            data = platform_config_service.delete_config(key)
            try:
                result = general_message(200, "success", "重置成功", bean=data)
            except Exception as e:
                logger.debug(e)
                raise ServiceHandleException(msg="update enterprise config failed", msg_show="重置失败")
        else:
            result = general_message(404, "can not delete key value", "该配置不可重置")
        return Response(result, status=result.get("code", 200))


class LogoView(BaseApiView):
    def get(self, request, *args, **kwargs):
        """
        获取云帮Logo
        ---
        """
        try:
            code = 200
            data = dict()
            logo = platform_config_service.get_config_by_key("LOGO")
            host_name = request.get_host()
            data["logo"] = str(host_name) + str(logo.value)
            result = general_message(code, "query success", "Logo获取成功", bean=data)
            return Response(result, status=code)
        except Exception as e:
            logger.exception(e)
            result = error_message(e.message)
        return Response(result)


class PhpConfigView(AlowAnyApiView):
    def get(self, request, *args, **kwargs):
        """获取php的环境配置"""

        versions = ["5.6.11", "5.6.30", "5.6.35", "7.0.16", "7.0.29", "7.1.2", "7.1.16"]
        default_version = "5.6.11"

        extends = [{
            "name": "BCMath",
            "value": "bcmath",
            "url": "http://docs.php.net/bcmath",
            "version": None
        }, {
            "name": "Calendar",
            "value": "calendar",
            "url": "http/docs.php.net/calendar",
            "version": None
        }, {
            "name": "Exif",
            "value": "exif",
            "url": "http://docs.php.net/exif",
            "version": "1.4"
        }, {
            "name": "FTP",
            "value": "ftp",
            "url": "http://docs.php.net/ftp",
            "version": None
        }, {
            "name": "GD(支持PNG, JPEG 和 FreeType)",
            "value": "gd",
            "url": "http://docs.php.net/gd",
            "version": "2.1.0"
        }, {
            "name": "gettext",
            "value": "gettext",
            "url": "http://docs.php.net/gettext",
            "version": None
        }, {
            "name": "intl",
            "value": "intl",
            "url": "http://docs.php.net/intl",
            "version": "1.1.0"
        }, {
            "name": "mbstring",
            "value": "mbstring",
            "url": "http://docs.php.net/mbstring",
            "version": "1.3.2"
        },
            {
                "name": "MySQL(PHP 5.5 版本已经停止支持，请使用 MySQLi 或 PDO)",
                "value": "mysql",
                "url": "http://docs.php.net/book.mysql",
                "version": "mysqlnd 5.0.11-dev"
            }, {
                "name": "PCNTL",
                "value": "pcntl",
                "url": "http://docs.php.net/pcntl",
                "version": None
            }, {
                "name": "Shmop",
                "value": "shmop",
                "url": "http://docs.php.net/shmop",
                "version": None
            }, {
                "name": "SOAP",
                "value": "soap",
                "url": "http://docs.php.net/soap",
                "version": None
            }, {
                "name": "SQLite3",
                "value": "sqlite3",
                "url": "http://docs.php.net/sqlite3",
                "version": "0.7-dev"
            }, {
                "name": "SQLite(PDO)",
                "value": "pdo_sqlite",
                "url": "http://docs.php.net/pdo_sqlite",
                "version": "3.8.2"
            }, {
                "name": "XMLRPC",
                "value": "xmlrpc",
                "url": "http://docs.php.net/xmlrpc",
                "version": "0.51"
            }, {
                "name": "XSL",
                "value": "xsl",
                "url": "http://docs.php.net/xsl",
                "version": "1.1.28"
            }, {
                "name": "APCu",
                "value": "apcu",
                "url": "http://pecl.php.net/package/apcu",
                "version": "4.0.6"
            }, {
                "name": "Blackfire",
                "value": "blackfire",
                "url": "http://blackfire.io/",
                "version": "0.20.6"
            }, {
                "name": "memcached",
                "value": "memcached",
                "url": "http://docs.php.net/memcached",
                "version": "2.2.0"
            }, {
                "name": "MongoDB",
                "value": "mongodb",
                "url": "http://docs.php.net/mongo",
                "version": "1.6.6"
            }, {
                "name": "NewRelic",
                "value": "newrelic",
                "url": "http://newrelic.com/php",
                "version": "4.19.0.90"
            }, {
                "name": "OAuth",
                "value": "oauth",
                "url": "http://docs.php.net/oauth",
                "version": "1.2.3"
            }, {
                "name": "PHPRedis",
                "value": "redis",
                "url": "http://pecl.php.net/package/redis",
                "version": "2.2.7"
            }]
        bean = {"versions": versions, "default_version": default_version, "extends": extends}
        return Response(general_message(200, "success", "查询成功", bean))


class InitPerms(AlowAnyApiView):
    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        enterprise_id = request.data.get("enterprise_id")
        tenant_id = request.data.get("tenant_id")
        if tenant_id and enterprise_id:
            teams = Tenants.objects.filter(tenant_id=tenant_id, enterprise_id=enterprise_id)
        elif tenant_id and not enterprise_id:
            teams = Tenants.objects.filter(tenant_id=tenant_id)
        elif not tenant_id and enterprise_id:
            teams = Tenants.objects.filter(enterprise_id=enterprise_id)
        else:
            teams = Tenants.objects.all()
        if not teams:
            print("未发现团队, 初始化结束")
            return
        for team in teams:
            role_kind_services.init_default_roles(kind="team", kind_id=team.tenant_id)
            users = team_repo.get_tenant_users_by_tenant_ID(team.ID)
            admin = role_kind_services.get_role_by_name(kind="team", kind_id=team.tenant_id, name="管理员")
            developer = role_kind_services.get_role_by_name(kind="team", kind_id=team.tenant_id, name="开发者")
            if not admin or not developer:
                raise ServiceHandleException(msg="init failed", msg_show="初始化失败")
            if users:
                for user in users:
                    if user.user_id == team.creater:
                        user_kind_role_service.update_user_roles(
                            kind="team", kind_id=team.tenant_id, user=user, role_ids=[admin.ID])
                    else:
                        user_kind_role_service.update_user_roles(
                            kind="team", kind_id=team.tenant_id, user=user, role_ids=[developer.ID])
        result = general_message(msg="success", msg_show="初始化权限分配成功", code=200)
        return Response(result, status=200)
