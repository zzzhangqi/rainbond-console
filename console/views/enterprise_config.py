# -*- coding: utf8 -*-
"""
  Created on 18/3/15.
"""
import json
import logging
import os

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.response import Response

from console.enum.system_config import ConfigKeyEnum
from console.exception.main import AbortRequest
from console.models.main import ConsoleSysConfig
from console.services.config_service import EnterpriseConfigService, ConfigService
from console.services.enterprise_services import enterprise_services
from www.utils.return_message import general_message
from console.utils.reqparse import bool_argument
from console.utils.reqparse import parse_item
from console.views.base import EnterpriseAdminView, JWTAuthApiView

logger = logging.getLogger("default")


class EnterpriseConfigLimitView(EnterpriseAdminView):
    def get(self, request, enterprise_id, *args, **kwargs):
        key = request.GET.get('key')
        configs = ConsoleSysConfig.objects.filter(key=key)
        if key == "personalLimit":
            ret_data = {
                "key": key,
                "value": {
                    "limit_cpu": {
                        "minValue": os.getenv("PERSONAL_LIMIT_MIN_CPU", 1000),
                        "maxValue": os.getenv("PERSONAL_LIMIT_MAX_CPU", 8000)
                    },
                    "limit_memory": {
                        "minValue": os.getenv("PERSONAL_LIMIT_MIN_MEMORY", 1024),
                        "maxValue": os.getenv("PERSONAL_LIMIT_MAX_MEMORY", 32768)
                    },
                    "limit_storage": {
                        "minValue": os.getenv("PERSONAL_LIMIT_MIN_STORAGE", 1),
                        "maxValue": os.getenv("PERSONAL_LIMIT_MAX_STORAGE", 300)
                    }
                },
                "desc": "企业级资源限额默认数据"
            }
        else:
            ret_data = {
                "key": key,
                "value": {
                    "limit_cpu": {
                        "minValue": os.getenv("ENTERPRISE_LIMIT_MIN_CPU", 1000),
                        "maxValue": os.getenv("ENTERPRISE_LIMIT_MAX_CPU", 40000)
                    },
                    "limit_memory": {
                        "minValue": os.getenv("ENTERPRISE_LIMIT_MIN_MEMORY", 1024),
                        "maxValue": os.getenv("ENTERPRISE_LIMIT_MAX_MEMORY", 131072)
                    },
                    "limit_storage": {
                        "minValue": os.getenv("ENTERPRISE_LIMIT_MIN_STORAGE", 1),
                        "maxValue": os.getenv("ENTERPRISE_LIMIT_MAX_STORAGE", 512)
                    }
                },
                "desc": "企业级资源限额默认数据"
            }
        if len(configs) != 0:
            config = configs[0]
            ret_data = {'key': config.key, 'value': json.loads(config.value), 'desc': config.desc}
        return Response(ret_data, status=status.HTTP_200_OK)

    def put(self, request, enterprise_id, *args, **kwargs):
        key = request.GET.get('key')
        data = request.data

        config, created = ConsoleSysConfig.objects.get_or_create(
            key=key,
            defaults={
                'type': 'json',
                'enable': 1,
                'desc': "企业级资源限额默认数据",
                'enterprise_id': enterprise_id
            }
        )
        if created:
            config.value = json.dumps(data)
            config.save()
            return Response(status=status.HTTP_201_CREATED,data=config.to_dict())
        else:
            config.value = json.dumps(data)
            config.save()
            return Response(status=status.HTTP_200_OK,data=config.to_dict())


class EnterpriseConfigView(EnterpriseAdminView):
    @never_cache
    def put(self, request, enterprise_id, *args, **kwargs):
        title = parse_item(request, "title")
        logo = parse_item(request, "logo")
        favicon = parse_item(request, "favicon")
        enterprise_alias = parse_item(request, "enterprise_alias")
        doc_url = parse_item(request, "doc_url")
        enable_official_demo = parse_item(request, "enable_official_demo", default=True)
        login_image = parse_item(request, "login_image")
        header_color = request.data.get("header_color", "")
        header_writing_color = request.data.get("header_writing_color", "")
        sidebar_color = request.data.get("sidebar_color", "")
        sidebar_writing_color = request.data.get("sidebar_writing_color", "")
        footer = request.data.get("footer", "")
        shadow = parse_item(request, "shadow", default=True)
        # 是否显示k8s集群相关
        show_k8s = parse_item(request, "show_k8s")
        # 是否显示切换语言
        show_langue = parse_item(request, "show_langue")

        config_service = ConfigService()
        ent_config_service = EnterpriseConfigService(enterprise_id)

        if title:
            config_service.update_config_value(ConfigKeyEnum.TITLE.name, title)
            ent_config_service.update_config_value(ConfigKeyEnum.TITLE.name, title)
        if logo:
            config_service.update_config_value(ConfigKeyEnum.LOGO.name, logo)
            ent_config_service.update_config_value(ConfigKeyEnum.LOGO.name, logo)
        if enterprise_alias:
            enterprise_services.update_alias(enterprise_id, enterprise_alias)
        if favicon:
            config_service.update_config_value(ConfigKeyEnum.FAVICON.name, favicon)
            ent_config_service.update_config_value(ConfigKeyEnum.FAVICON.name, favicon)
        if login_image:
            config_service.update_config_value(ConfigKeyEnum.LOGIN_IMAGE.name, login_image)
            ent_config_service.update_config_value(ConfigKeyEnum.LOGIN_IMAGE.name, login_image)
        if type(show_k8s) == bool:
            ent_config_service.update_config_enable_status(ConfigKeyEnum.SHOW_K8S.name, show_k8s)
        if type(show_langue) == bool:
            ent_config_service.update_config_enable_status(ConfigKeyEnum.SHOW_LANGUE.name, show_langue)

        config_service.update_config_value(ConfigKeyEnum.HEADER_COLOR.name, header_color)
        ent_config_service.update_config_value(ConfigKeyEnum.HEADER_COLOR.name, header_color)

        config_service.update_config_value(ConfigKeyEnum.HEADER_WRITING_COLOR.name, header_writing_color)
        ent_config_service.update_config_value(ConfigKeyEnum.HEADER_WRITING_COLOR.name, header_writing_color)

        config_service.update_config_value(ConfigKeyEnum.SIDEBAR_COLOR.name, sidebar_color)
        ent_config_service.update_config_value(ConfigKeyEnum.SIDEBAR_COLOR.name, sidebar_color)

        config_service.update_config_value(ConfigKeyEnum.SIDEBAR_WRITING_COLOR.name, sidebar_writing_color)
        ent_config_service.update_config_value(ConfigKeyEnum.SIDEBAR_WRITING_COLOR.name, sidebar_writing_color)

        config_service.update_config_value(ConfigKeyEnum.FOOTER.name, footer)
        ent_config_service.update_config_value(ConfigKeyEnum.FOOTER.name, footer)

        config_service.update_config_value(ConfigKeyEnum.SHADOW.name, shadow)
        ent_config_service.update_config_enable_status(ConfigKeyEnum.SHADOW.name, shadow)

        doc_url_value = dict()
        doc_url_value["platform_url"] = ""
        if doc_url:
            if not doc_url.startswith(('http://', 'https://')):
                doc_url = "http://{}".format(doc_url)
            if not doc_url.endswith('/'):
                doc_url = doc_url + '/'
            doc_url_value["platform_url"] = doc_url
        ent_config_service.update_config_value(ConfigKeyEnum.DOCUMENT.name, doc_url_value)
        ent_config_service.update_config_enable_status(ConfigKeyEnum.OFFICIAL_DEMO.name, enable_official_demo)
        config_service.update_config_value(ConfigKeyEnum.DOCUMENT.name, doc_url_value)
        config_service.update_config_enable_status(ConfigKeyEnum.OFFICIAL_DEMO.name, enable_official_demo)

        return Response(status=status.HTTP_200_OK)


class EnterpriseObjectStorageView(EnterpriseAdminView):
    @never_cache
    def put(self, request, enterprise_id, *args, **kwargs):
        enable = bool_argument(parse_item(request, "enable", required=True))
        provider = parse_item(request, "provider", required=True)
        endpoint = parse_item(request, "endpoint", required=True)
        bucket_name = parse_item(request, "bucket_name", required=True)
        access_key = parse_item(request, "access_key", required=True)
        secret_key = parse_item(request, "secret_key", required=True)

        if provider not in ("alioss", "s3"):
            raise AbortRequest("provider {} not in (\"alioss\", \"s3\")".format(provider))

        ent_cfg_svc = EnterpriseConfigService(enterprise_id)
        ent_cfg_svc.update_config_enable_status(key="OBJECT_STORAGE", enable=enable)
        ent_cfg_svc.update_config_value(
            key="OBJECT_STORAGE",
            value={
                "provider": provider,
                "endpoint": endpoint,
                "bucket_name": bucket_name,
                "access_key": access_key,
                "secret_key": secret_key,
            })
        return Response(status=status.HTTP_200_OK)


class EnterpriseAppStoreImageHubView(EnterpriseAdminView):
    @never_cache
    def put(self, request, enterprise_id, *args, **kwargs):
        enable = bool_argument(parse_item(request, "enable", required=True))
        hub_url = parse_item(request, "hub_url", required=True)
        namespace = parse_item(request, "namespace")
        hub_user = parse_item(request, "hub_user")
        hub_password = parse_item(request, "hub_password")

        ent_cfg_svc = EnterpriseConfigService(enterprise_id)
        ent_cfg_svc.update_config_enable_status(key="APPSTORE_IMAGE_HUB", enable=enable)
        ent_cfg_svc.update_config_value(
            key="APPSTORE_IMAGE_HUB",
            value={
                "hub_url": hub_url,
                "namespace": namespace,
                "hub_user": hub_user,
                "hub_password": hub_password,
            })
        return Response(status=status.HTTP_200_OK)


class EnterpriseVisualMonitorView(EnterpriseAdminView):
    @never_cache
    def put(self, request, enterprise_id, *args, **kwargs):
        enable = bool_argument(parse_item(request, "enable", required=True))
        home_url = parse_item(request, "home_url", required=True)
        cluster_monitor_suffix = request.data.get("cluster_monitor_suffix", "/d/cluster/ji-qun-jian-kong-ke-shi-hua")
        node_monitor_suffix = request.data.get("node_monitor_suffix", "/d/node/jie-dian-jian-kong-ke-shi-hua")
        component_monitor_suffix = request.data.get("component_monitor_suffix", "/d/component/zu-jian-jian-kong-ke-shi-hua")
        slo_monitor_suffix = request.data.get("slo_monitor_suffix", "/d/service/fu-wu-jian-kong-ke-shi-hua")

        ent_cfg_svc = EnterpriseConfigService(enterprise_id)
        ent_cfg_svc.update_config_enable_status(key="VISUAL_MONITOR", enable=enable)
        ent_cfg_svc.update_config_value(
            key="VISUAL_MONITOR",
            value={
                "home_url": home_url.strip('/'),
                "cluster_monitor_suffix": cluster_monitor_suffix,
                "node_monitor_suffix": node_monitor_suffix,
                "component_monitor_suffix": component_monitor_suffix,
                "slo_monitor_suffix": slo_monitor_suffix,
            })
        return Response(status=status.HTTP_200_OK)


class EnterpriseAlertsView(JWTAuthApiView):
    @never_cache
    def get(self, request, enterprise_id, *args, **kwargs):
        alerts = enterprise_services.get_enterprise_alerts(enterprise_id)
        return Response(general_message(200, "success", "查询成功", list=alerts), status=status.HTTP_200_OK)
