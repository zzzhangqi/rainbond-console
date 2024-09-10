# -*- coding: utf-8 -*-
import logging

import yaml
from rest_framework.response import Response
from console.repositories.init_cluster import rke_cluster, rke_cluster_node
from console.utils.k8s_cli import K8sClient
from console.views.base import AlowAnyApiView
from www.utils.return_message import general_message

logger = logging.getLogger("default")


class BaseClusterView(AlowAnyApiView):
    def handle_exception(self, e, message="Operation failed", message_cn="操作失败"):
        logger.error(f"{message}: {str(e)}")
        result = general_message(500, message, message_cn, bean={"error": str(e)})
        return Response(result, status=500)


# 获取集群部署状态的接口
class ClusterRKE(BaseClusterView):
    # get 接口用于获取集群安装状态以及初始化安装集群。
    def get(self, request):
        try:
            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            result = general_message(200, "Get cluster successful.", "获取集群成功", bean={
                "event_id": cluster.event_id,
                "create_status": cluster.create_status,
            })
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to get cluster", "获取集群失败")

    # put 接口用于更新集群的配置文件，脚本执行完成后调用。
    def put(self, request):
        kubeconfig_file = request.FILES.get('kubeconfig')
        if not kubeconfig_file:
            result = general_message(400, "No kubeconfig file provided.", "未提供kubeconfig文件")
            return Response(result, status=400)

        try:
            kubeconfig_content = kubeconfig_file.read().decode('utf-8')
            server_node = rke_cluster_node.get_server_node()
            kubeconfig_content.replace("127.0.0.1", server_node.node_name)
            cluster = rke_cluster.update_cluster(kubeconfig_content, "installing")
            nodes = rke_cluster_node.get_worker_node(cluster.cluster_name)
            k8s_api = K8sClient(cluster.config)
            k8s_api.nodes_add_worker_rule(nodes)
            result = general_message(200, "Cluster updated successfully.", "集群更新成功")
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to update cluster", "集群更新失败")


# 节点注册接口
class InstallRKECluster(BaseClusterView):
    def get(self, request):
        try:
            node_ip = request.GET.get("node_ip", "")
            node_role = request.GET.get("node_role", "")
            node_name = request.GET.get("node_name", "")
            node_role_list = node_role.split(",")
            is_server = False
            node = None
            if "controlplane" in node_role_list:
                cluster, is_server = rke_cluster.only_server(node_ip)
            else:
                cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if cluster.server_host:
                node = rke_cluster_node.create_node(cluster.cluster_name, cluster.server_host, node_name, node_role, node_ip)

            if cluster.config and "worker" in node_role_list and node:
                k8s_api = K8sClient(cluster.config)
                k8s_api.nodes_add_worker_rule([node])

            result = general_message(200, "Nodes init successfully.", "节点注册成功",
                                     bean={"server_ip": cluster.server_host, "is_server": is_server})
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to retrieve nodes", "节点注册失败")


# 获取节点信息接口
class ClusterRKENode(BaseClusterView):
    def get(self, request):
        try:
            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if not cluster.config:
                result = general_message(200, "No cluster config available.", "无可用的集群配置", bean=[])
                return Response(result, status=200)

            k8s_api = K8sClient(cluster.config)
            nodes = k8s_api.get_nodes()
            nodeReady = all(node.get("status") == "Ready" for node in nodes)
            if nodeReady and nodes:
                rke_cluster.update_cluster("", "installed")
            else:
                rke_cluster.update_cluster("", "installing")
            result = general_message(200, "Nodes retrieved successfully.", "节点获取成功", bean=nodes)
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to retrieve nodes", "获取节点失败")


# 获取节点IP接口
class ClusterNodeIP(BaseClusterView):
    def get(self, request):
        try:
            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if not cluster.config:
                result = general_message(200, "No cluster config available.", "无可用的集群配置", bean=[])
                return Response(result, status=200)
            nodes = rke_cluster_node.get_cluster_nodes(cluster.cluster_name)
            ips = [node.node_name for node in nodes]
            result = general_message(200, "Nodes retrieved successfully.", "节点 ip 获取成功", list=ips)
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to retrieve nodes", "获取节点失败")


# 安装 Rainbond
class ClusterRKEInstallRB(BaseClusterView):
    def post(self, request):
        try:
            # 从请求体中获取 values.yaml 内容
            values_content = request.data.get('value_yaml')
            if not values_content:
                result = general_message(400, "No values.yaml content provided.", "未提供 values.yaml 内容", bean=[])
                return Response(result, status=400)

            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if not cluster.config:
                result = general_message(200, "No cluster config available.", "无可用的集群配置", bean=[])
                return Response(result, status=200)

            k8s_api = K8sClient(cluster.config)
            error_message = k8s_api.install_rainbond(values_content)
            if error_message:
                return self.handle_exception(error_message, "Failed to install Rainbond", "安装Rainbond失败")
            cluster.create_status = "integrating"
            cluster.save()
            result = general_message(200, "Rainbond installed successfully.", "Rainbond安装成功", bean={})
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to install Rainbond", "安装Rainbond失败")


# 卸载 Rainbond
class ClusterRKEUNInstallInstallRB(BaseClusterView):
    def post(self, request):
        try:
            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if not cluster.config:
                result = general_message(200, "No cluster config available.", "无可用的集群配置", bean=[])
                return Response(result, status=200)

            k8s_api = K8sClient(cluster.config)
            error_message = k8s_api.uninstall_rainbond()
            if error_message:
                return self.handle_exception(error_message, "Failed to install Rainbond", "卸载Rainbond失败")
            cluster.create_status = "installed"
            cluster.save()
            result = general_message(200, "Rainbond installed successfully.", "Rainbond卸载成功", bean={})
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to install Rainbond", "安装Rainbond失败")


# 获取 Rainbond 安装状态
class ClusterRKERBStatus(BaseClusterView):
    def get(self, request):
        try:
            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if not cluster.config:
                result = general_message(200, "No cluster config available.", "无可用的集群配置", bean=[])
                return Response(result, status=200)
            k8s_api = K8sClient(cluster.config)
            rb_components_status, rb_installed = k8s_api.rb_components_status()
            if rb_installed:
                cluster.create_status = "integrated"
                cluster.save()
            result = general_message(200, "get rb components status successfully.", "组件状态获取成功",
                                     bean=rb_components_status)
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to get cluster", "获取组件状态失败")


# 获取 Rainbond 组件的详细事件信息
class ClusterRKERBEvent(BaseClusterView):
    def get(self, request):
        try:
            pod_name = request.GET.get('pod_name')
            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if not cluster.config:
                result = general_message(200, "No cluster config available.", "无可用的集群配置", bean=[])
                return Response(result, status=200)
            k8s_api = K8sClient(cluster.config)
            rb_components_status = k8s_api.rb_component_event(pod_name)
            result = general_message(200, "get rb components status successfully.", "组件状态获取成功",
                                     bean=rb_components_status)
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to get cluster", "获取组件状态失败")


# 获取 Rainbond 集群信息
class RKERegionConfig(BaseClusterView):
    def get(self, request):
        try:
            cluster = rke_cluster.get_rke_cluster_exclude_integrated()
            if not cluster.config:
                result = general_message(200, "No cluster config available.", "无可用的集群配置", bean=[])
                return Response(result, status=200)
            k8s_api = K8sClient(cluster.config)
            region_config = k8s_api.rb_region_config()
            region_config_yaml = yaml.dump(region_config, default_flow_style=False, allow_unicode=True)
            result = general_message(200, "get rb region config successfully.", "集群配置信息获取成功",
                                     bean={"configs": region_config, "configs_yaml": region_config_yaml})
            return Response(result, status=200)
        except Exception as e:
            return self.handle_exception(e, "Failed to get region config", "集群配置信息获取失败")
