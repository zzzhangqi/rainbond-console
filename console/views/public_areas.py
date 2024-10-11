# -*- coding: utf-8 -*-
import logging
from functools import cmp_to_key

from console.exception.exceptions import GroupNotExistError
from console.repositories.group import group_repo
from console.repositories.region_app import region_app_repo
from console.repositories.region_repo import region_repo
from console.repositories.service_repo import service_repo
from console.services.app_actions.app_log import AppEventService
from console.services.common_services import common_services
from console.services.group_service import group_service
from console.services.service_services import base_service
from console.services.team_services import team_services
from console.services.user_accesstoken_services import user_access_services
from console.views.base import RegionTenantHeaderView, JWTAuthApiView
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import connection
from django.views.decorators.cache import never_cache
from goodrain_web.tools import JuncheePaginator
from rest_framework.response import Response
from www.apiclient.regionapi import RegionInvokeApi
from www.models.main import RegionApp
from www.utils.return_message import general_message
from www.utils.status_translate import get_status_info_map

event_service = AppEventService()

region_api = RegionInvokeApi()

logger = logging.getLogger('default')


class AllServiceInfo(RegionTenantHeaderView):
    def post(self, request, *args, **kwargs):
        """
        查看总览分页页面应用状态信息(弃)
        ---
        parameters:
            - name: team_name
              description: 团队名
              required: true
              type: string
              paramType: path
            - name: service_ids
              description: 当前页面应用ID列表 格式{"service_ids": ["1","2"]}
              required: true
              type: string
              paramType: form
        """
        code = 200
        service_ids = request.data["service_ids"]
        status_list = []
        if len(service_ids) > 0:
            status_list = base_service.status_multi_service(
                region=self.response_region,
                tenant_name=self.team_name,
                service_ids=service_ids,
                enterprise_id=self.team.enterprise_id)
        result = general_message(code, "success", "批量获取状态成功", list=status_list)
        return Response(result, status=code)


class TeamArchView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        res, body = region_api.get_cluster_nodes_arch(self.region_name)
        result = general_message(200, "success", "架构获取成功", list=list(set(body.get("list"))))
        return Response(result, status=200)


class TeamOverView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        count_data = dict()
        users = team_services.get_team_users(self.team)
        team_service_num = service_repo.get_team_service_num_by_team_id(self.team.tenant_id, self.response_region)
        count_data["team_service_num"] = team_service_num
        count_data["user_nums"] = users.count()
        count_data["team_app_num"] = len(self.perm_apps)
        count_data["logo"] = self.team.logo
        if self.perm_apps[0] == -1:
            groups = group_repo.get_tenant_region_groups(self.team.tenant_id, self.region_name, app_ids=self.perm_apps)
            count_data["team_app_num"] = groups.count()
        count_data["team_alias"] = self.tenant.tenant_alias
        count_data["team_id"] = self.team.tenant_id
        return Response(general_message(200, "success", "查询成功", bean=count_data))


class ServiceGroupView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        """
        应用列表
        ---
        parameters:
            - name: team_name
              description: 团队名
              required: true
              type: string
              paramType: path
            - name: query
              description: 应用搜索名称
              required: false
              type: string
              paramType: query
        """
        code = 200
        query = request.GET.get("query", "")
        app_type = request.GET.get("app_type", "")
        groups_services = group_service.get_groups_and_services(self.tenant, self.response_region, query, app_type)
        return Response(general_message(200, "success", "查询成功", list=groups_services), status=code)


class GroupOperatorManagedView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        """
        纳管当前应用经用户Operator处理创建的资源
        """
        group_id = request.GET.get("group_id", None)
        code = 200
        operator_managed = group_service.get_watch_managed_data(self.tenant, self.region_name, group_id)
        result = general_message(code, "success", "获取成功", list=operator_managed)
        return Response(result, status=code)


class GroupServiceView(RegionTenantHeaderView):
    @never_cache
    def get(self, request, *args, **kwargs):
        """
        应用组件列表、状态展示
        ---
        parameters:
            - name: team_name
              description: 团队名
              required: true
              type: string
              paramType: path
            - name: page
              description: 页数(默认第一页)
              required: false
              type: string
              paramType: query
            - name: page_size
              description: 每页展示个数(默认10个)
              required: false
              type: string
              paramType: query
            - name: group_id
              description: 应用id
              required: true
              type: string
              paramType: query
        """
        try:
            code = 200
            sort = int(request.GET.get("sort", 1))
            order = request.GET.get("order", "descend")
            page = request.GET.get("page", 1)
            page_size = request.GET.get("page_size", 10)
            group_id = request.GET.get("group_id", None)
            if group_id is None or not group_id.isdigit():
                code = 400
                result = general_message(code, "group_id is missing or not digit!", "group_id缺失或非数字")
                return Response(result, status=code)

            query = request.GET.get("query", "")

            if group_id == "-1":
                # query service which not belong to any app
                no_group_service_list = service_repo.get_no_group_service_status_by_group_id(
                    team_name=self.team_name,
                    team_id=self.team.tenant_id,
                    region_name=self.response_region,
                    enterprise_id=self.team.enterprise_id)
                if page_size == "-1" or page_size == "" or page_size == "0":
                    page_size = len(no_group_service_list) if len(no_group_service_list) > 0 else 10
                paginator = Paginator(no_group_service_list, page_size)
                try:
                    no_group_service_list = paginator.page(page).object_list
                except PageNotAnInteger:
                    no_group_service_list = paginator.page(1).object_list
                except EmptyPage:
                    no_group_service_list = paginator.page(paginator.num_pages).object_list
                result = general_message(code, "query success", "应用查询成功", list=no_group_service_list, total=paginator.count)
                return Response(result, status=code)

            team_id = self.team.tenant_id
            group_count = group_repo.get_group_count_by_team_id_and_group_id(team_id=team_id, group_id=group_id)
            if group_count == 0:
                result = general_message(202, "group is not yours!", "当前组已删除或您无权限查看！", bean={})
                return Response(result, status=200)

            group_service_list = service_repo.get_group_service_by_group_id(
                group_id=group_id,
                region_name=self.response_region,
                team_id=self.team.tenant_id,
                team_name=self.team_name,
                enterprise_id=self.team.enterprise_id,
                query=query)
            if page_size == "-1" or page_size == "" or page_size == "0":
                page_size = len(group_service_list) if len(group_service_list) > 0 else 10
            paginator = Paginator(group_service_list, page_size)
            try:
                group_service_list = paginator.page(page).object_list
            except PageNotAnInteger:
                group_service_list = paginator.page(1).object_list
            except EmptyPage:
                group_service_list = paginator.page(paginator.num_pages).object_list
            result = general_message(code, "query success", "应用查询成功", list=group_service_list, total=paginator.count)
            if sort == 3:
                if order == "ascend":
                    group_service_list = sorted(group_service_list, key=lambda i: i["update_time"])
            elif sort == 2:
                if order == "ascend":
                    group_service_list = sorted(
                        group_service_list,
                        key=lambda i: (i["min_memory"], -1 if i["status"] == "running" else -2 if i["status"] == "abonrmal" else
                                       -3 if i["status"] == "starting" else -5 if i["status"] == "closed" else -4))
                else:
                    group_service_list = sorted(
                        group_service_list,
                        key=lambda i: (-i["min_memory"], 1 if i["status"] == "running" else 2 if i["status"] == "abonrmal" else
                                       3 if i["status"] == "starting" else 5 if i["status"] == "closed" else 4))
            else:
                if order == "ascend":
                    group_service_list = sorted(
                        group_service_list,
                        key=lambda i: (-1 if i["status"] == "running" else -2 if i["status"] == "abnormal" else -3 if i[
                            "status"] == "starting" else -5 if i["status"] == "closed" else -4, i["min_memory"]))
                else:
                    group_service_list = sorted(
                        group_service_list,
                        key=lambda i: (1 if i["status"] == "running" else 2 if i["status"] == "abnormal" else 3
                                       if i["status"] == "starting" else 5 if i["status"] == "closed" else 4, -i["min_memory"]))
            return Response(result, status=code)
        except GroupNotExistError as e:
            logger.exception(e)
            result = general_message(400, "query success", "该应用不存在")
            return Response(result, status=400)


class ServiceEventsView(RegionTenantHeaderView):
    def __sort_events(self, event1, event2):
        event1_start_time = event1.get("StartTime") if isinstance(event1, dict) else event1.start_time
        event2_start_time = event2.get("StartTime") if isinstance(event2, dict) else event2.start_time
        if event1_start_time < event2_start_time:
            return 1
        if event1_start_time > event2_start_time:
            return -1
        if event1_start_time == event2_start_time:
            event1_ID = event1.get("ID") if isinstance(event1, dict) else event1.ID
            event2_ID = event2.get("ID") if isinstance(event2, dict) else event2.ID
            if event1_ID < event2_ID:
                return 1
            if event1_ID > event2_ID:
                return -1
            return 0

    def get(self, request, *args, **kwargs):
        """
        组件事件动态
        ---
        parameters:
            - name: team_name
              description: 团队名
              required: true
              type: string
              paramType: path
            - name: page
              description: 页数(默认第一页)
              required: false
              type: string
              paramType: query
            - name: page_size
              description: 每页展示个数(默认3个)
              required: false
              type: string
              paramType: query
        """
        page = request.GET.get("page", 1)
        page_size = request.GET.get("page_size", 3)
        total = 0
        region_list = region_repo.get_team_opened_region(self.tenant.tenant_name)
        event_service_dynamic_list = []
        if region_list:
            for region in region_list:
                try:
                    events, event_count, has_next = event_service.get_target_events("tenant", self.tenant.tenant_id,
                                                                                    self.tenant, region.region_name, int(page),
                                                                                    int(page_size))
                    event_service_dynamic_list = event_service_dynamic_list + events
                    total = total + event_count
                except Exception as e:
                    logger.error("Region api return error {0}, ignore it".format(e))

        event_service_dynamic_list = sorted(event_service_dynamic_list, key=cmp_to_key(self.__sort_events))

        service_ids = []
        for event in event_service_dynamic_list:
            if event["Target"] == "service":
                service_ids.append(event["TargetID"])

        services = service_repo.list_by_component_ids(service_ids)

        event_service_list = []
        for event in event_service_dynamic_list:
            if event["Target"] == "service":
                for service in services:
                    if service.service_id == event["TargetID"]:
                        event["service_alias"] = service.service_alias
                        event["service_name"] = service.service_cname
            event_service_list.append(event)

        event_paginator = JuncheePaginator(event_service_list, int(page_size))
        event_page_list = event_paginator.page(page)
        total = event_paginator.count
        event_list = [event for event in event_page_list]
        result = general_message(200, 'success', "查询成功", list=event_list, total=total)
        return Response(result, status=result["code"])


class TeamServiceOverViewView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        """
        总览 团队应用信息 + 分页 + 排序 + 模糊查询
        ---
        parameters:
            - name: team_name
              description: 团队名
              required: true
              type: string
              paramType: path
            - name: page
              description: 页数(默认第一页)
              required: false
              type: string
              paramType: query
            - name: page_size
              description: 每页展示个数(默认10个)
              required: false
              type: string
              paramType: query
            - name: order
              description: 排序规则 desc(从大到小)或者asc(从小到大) 默认desc
              required: false
              type: string
              paramType: query
            - name: fields
              description: 排序字段 默认 update_time 可用(update_time, min_memory)
              required: false
              type: string
              paramType: query
            - name: query_key
              description: 模糊组件名 默认为空，查到所有组件
              required: false
              type: string
              paramType: query
            - name: service_status
              description: 组件状态 默认all 可用(running, closed, all)
              required: true
              type: string
              paramType: query
        """
        code = 200
        page = request.GET.get("page", 1)
        page_size = request.GET.get("page_size", 10)
        order = request.GET.get('order_type', 'desc')
        fields = request.GET.get('fields', 'update_time')
        query_key = request.GET.get("query_key", '')
        service_status = request.GET.get("service_status", 'all')
        if not self.team:
            result = general_message(400, "failed", "该团队不存在")
            return Response(result, status=400)
        services_list = base_service.get_fuzzy_services_list(
            team_id=self.team.tenant_id, region_name=self.response_region, query_key=query_key, fields=fields, order=order)
        if services_list:
            try:
                service_ids = [service["service_id"] for service in services_list]
                status_list = base_service.status_multi_service(
                    region=self.response_region,
                    tenant_name=self.team_name,
                    service_ids=service_ids,
                    enterprise_id=self.team.enterprise_id)
                status_cache = {}
                statuscn_cache = {}
                for status in status_list:
                    status_cache[status["service_id"]] = status["status"]
                    statuscn_cache[status["service_id"]] = status["status_cn"]
                result = []
                for service in services_list:
                    if service["group_id"] is None:
                        service["group_name"] = "未分组"
                        service["group_id"] = "-1"
                    if service_status == "all":
                        service["status_cn"] = statuscn_cache.get(service["service_id"], "未知")
                        status = status_cache.get(service["service_id"], "unknow")
                        if status == "unknow" and service["create_status"] != "complete":
                            service["status"] = "creating"
                            service["status_cn"] = "创建中"
                        else:
                            service["status"] = status_cache.get(service["service_id"], "unknow")
                            service["status_cn"] = get_status_info_map(service["status"]).get("status_cn")
                        if service["status"] == "closed" or service["status"] == "undeploy":
                            service["min_memory"] = 0
                        result.append(service)
                    else:
                        if status_cache.get(service.service_id) == service_status:
                            service["status"] = status_cache.get(service.service_id, "unknow")
                            service["status_cn"] = get_status_info_map(service["status"]).get("status_cn")
                            if service["status"] == "closed" or service["status"] == "undeploy":
                                service["min_memory"] = 0
                            result.append(service)
                paginator = Paginator(result, page_size)
                try:
                    result = paginator.page(page).object_list
                except PageNotAnInteger:
                    result = paginator.page(1).object_list
                except EmptyPage:
                    result = paginator.page(paginator.num_pages).object_list
                result = general_message(200, "query user success", "查询用户成功", list=result, total=paginator.count)
            except Exception as e:
                logger.exception(e)
                return Response(services_list, status=200)
            return Response(result, status=code)
        else:
            result = general_message(200, "success", "当前团队没有创建应用")
            return Response(result, status=200)


class TeamAppNamesView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        groups = group_repo.get_tenant_region_groups(self.team.tenant_id, self.response_region, "")
        group_k8s_app_names = [app.k8s_app for app in groups]
        data = {"app_names": group_k8s_app_names}
        return Response(general_message(200, "success", "查询成功", bean=data), status=200)


class TeamAppSortViewView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        """
        总览 团队应用信息
        """
        query = request.GET.get("query", "")
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 10))
        sort = int(request.GET.get("sort", 2))
        apps = list()
        all_group = group_repo.get_tenant_region_groups(self.team.tenant_id, self.response_region, query,
                                                        app_ids=self.perm_apps)
        start = (page - 1) * page_size
        end = page * page_size

        if sort == 2:
            groups = all_group[start:end]
            for app in groups:
                apps.append({
                    "group_id": app.ID,
                    "update_time": app.update_time,
                    "create_time": app.create_time,
                    "group_name": app.group_name,
                    "service_list": [],
                })
        if sort == 1:
            status_order = {
                'RUNNING': 1,
                'ABNORMAL': 2,
                'STARTING': 3,
                'CLOSED': 4
            }
            group_ids = all_group.values_list("ID", flat=True)
            re_app_dict = group_service.get_region_app_statuses(self.tenant_name, self.region_name, group_ids)
            sorted_app_list = sorted(re_app_dict.values(), key=lambda x: status_order.get(x['status'], 5))
            sorted_app_list = sorted_app_list[start:end]
            group_id_dict = {sorted_app.get("group_id"): {} for sorted_app in sorted_app_list}
            if group_ids:
                groups = group_repo.get_tenant_region_groups(self.team.tenant_id, self.response_region, query, app_ids=list(group_id_dict.keys()))
            else:
                groups = all_group[start:end]
            for app in groups:
                group_id_dict[app.ID] = {
                    "group_id": app.ID,
                    "update_time": app.update_time,
                    "create_time": app.create_time,
                    "group_name": app.group_name,
                    "service_list": [],
                }
            apps = list(group_id_dict.values())
        return Response(general_message(200, "success", "查询成功", list=apps), status=200)


# 团队下应用环境变量模糊查询
class TenantServiceEnvsView(RegionTenantHeaderView):
    def get(self, request, *args, **kwargs):
        attr_name = request.GET.get("attr_name", None)
        attr_value = request.GET.get("attr_value", None)
        if not attr_name and not attr_value:
            result = general_message(400, "parameter is null", "参数缺失")
            return Response(result)
        if attr_name and attr_value:
            result = general_message(400, "failed", "变量名和值不能同时存在")
            return Response(result)
        # 查询变量名
        if attr_name:
            attr_name_list = []
            cursor = connection.cursor()
            cursor.execute("""
                select attr_name from tenant_service_env_var
                where tenant_id='{0}' and attr_name like '%{1}%'
                order by attr_name;
                """.format(self.team.tenant_id, attr_name))
            service_envs = cursor.fetchall()
            if len(service_envs) > 0:
                for service_env in service_envs:
                    if service_env[0] not in attr_name_list:
                        attr_name_list.append(service_env[0])
            result = general_message(200, "success", "查询成功", list=attr_name_list)
            return Response(result)

        # 查询变量值
        if attr_value:
            attr_value_list = []
            cursor = connection.cursor()
            cursor.execute("""
                select attr_value from tenant_service_env_var
                where tenant_id='{0}' and attr_value like '%{1}%'
                order by attr_value;
                """.format(self.team.tenant_id, attr_value))
            service_envs = cursor.fetchall()
            if len(service_envs) > 0:
                for service_env in service_envs:
                    if service_env[0] not in attr_value_list:
                        attr_value_list.append(service_env[0])
            result = general_message(200, "success", "查询成功", list=attr_value_list)
            return Response(result)


class AccessTokenView(JWTAuthApiView):
    def get(self, request, team_name, token_note, **kwargs):
        access_key = user_access_services.get_user_access_key_by_note(request.user.user_id, token_note).first()
        if not access_key:
            try:
                access_key = user_access_services.create_user_access_key(token_note, request.user.user_id, "")
            except ValueError as e:
                logger.exception(e)
                raise e
        result = general_message(200, "success", None, bean=access_key.to_dict())
        return Response(result, status=200)
