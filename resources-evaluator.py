import os
from kubernetes import client
from kubernetes.client.rest import ApiException
from openshift.dynamic import DynamicClient
from openshift.helper.userpassauth import OCPLoginConfiguration
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from getpass import getpass
import csv
import re

# Disable SSL Warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class ResourceEvaluator:
  
  def __init__(self, user, pwd, apiURL):
    
    self.user = user
    self.pwd = pwd
    self.apiURL = apiURL
    self.acronyms = [] 
    self.projects = []
    self.deployments = []
    self.client = self.get_client()
    self.dynamic_client = DynamicClient(self.client)

  def oc_login(self):
    self.kubeConfig = OCPLoginConfiguration(ocp_username=self.user, ocp_password=self.pwd)
    self.kubeConfig.host = self.apiURL
    self.kubeConfig.verify_ssl = False
    self.kubeConfig.get_token()
    return client.ApiClient(self.kubeConfig)

  def get_client(self):
    return self.oc_login()
    
  def get_acronyms(self, filename):
    # open file containing acronyms
    with open(filename) as file:
     # print(file.readlines())
      acronyms = file.readlines()
      for line in acronyms:
        self.acronyms.append(line.strip())
      # print(self.acronyms)

  def get_ns(self):
    self.get_acronyms('acronyms.txt')
    projects = self.dynamic_client.resources.get(api_version='project.openshift.io/v1', kind='Project')
    projects_list = projects.get()
    for acronym in self.acronyms:
      # find namespaces
      for project in projects_list.items:
        if acronym in project.metadata.name:
          self.projects.append(project.metadata.name)

  def get_deployments(self):
    deployments = self.dynamic_client.resources.get(api_version='apps/v1', kind='Deployment')
    deployment_configs = self.dynamic_client.resources.get(api_version='apps.openshift.io/v1', kind='DeploymentConfig')
    # stateful_sets = self.dynamic_client.resources.get(api_version='apps/v1', kind='StatefulSet')
    # replica_sets = self.dynamic_client.resources.get(api_version='apps/v1', kind='ReplicaSet')
    # for each namespace build a list of dc/deployments/sts or replica sets
    for project in self.projects:
      try:
        target_deployments = deployments.get(namespace=project)
        target_dc = deployment_configs.get(namespace=project)
        # target_sts = stateful_sets.get(namespace=project)
        # target_rs = replica_sets.get(namespace=project)
        if target_deployments:
          self.deployments.extend(target_deployments.items)
        if target_dc:
          self.deployments.extend(target_dc.items)
        # if len(target_sts):
        #   self.deployments.extend(target_sts.items)
        # if len(target_rs):
        #   self.deployments.extend(target_rs.items)
      except ApiException as error:
        print(error)


  def get_resources_info(self, namespace, deployment, outputfile):
    # for each deployment in a namespace collect: replicas, resource limits and requests, hpa max and min, maxSurge
    # if limits and requests are not specified, get the limits resource in the namespace --> limit range default (=limits) and default requests (=requests)
    replicas = deployment.spec.replicas
    max_surge = ''
    if deployment.spec.strategy.rollingParams and deployment.spec.strategy.rollingParams.maxSurge:
        max_surge = deployment.spec.strategy.rollingParams.maxSurge
    else:
      if deployment.spec.strategy.rollingUpdate and deployment.spec.strategy.rollingUpdate.maxSurge:
        max_surge = deployment.spec.strategy.rollingUpdate.maxSurge
    requests = ['','']
    limits = ['','']
    hpa_max = ''
    hpa_min = '' 
    target_cpu = ''
    current_cpu = ''
    try:
      resources = self.dynamic_client.resources.get(api_version='v1', kind='LimitRange')
      target_resources = resources.get(namespace=namespace)
      # print(target_resources)
      for resource in target_resources.items:
        print(resource.spec.limits[1])
        requests[0] = resource.spec.limits[1].defaultRequest.cpu
        requests[1] = resource.spec.limits[1].defaultRequest.memory
        limits[0] = resource.spec.limits[1].default.cpu
        limits[1] = resource.spec.limits[1].default.memory
      # print(requests)
      # print(limits)
    except ApiException as e:
      print(e)
    for container in deployment.spec.template.spec.containers:
      if container.resources and container.resources.requests:
        if container.resources.requests.cpu:
          cpu_converted = self.convert_cpu_value(container.resources.requests.cpu)
          requests[0] += cpu_converted
        if container.resources.requests.memory:
          memory_converted = self.convert_memory_value(container.resources.requests.memory)
          requests[1] += memory_converted
      if container.resources and container.resources.limits:
        if container.resources.limits.cpu:
          cpu_converted = self.convert_cpu_value(container.resources.limits.cpu)
          limits[0] += cpu_converted
        if container.resources.limits.memory:
          memory_converted = self.convert_memory_value(container.resources.limits.memory)
          limits[1] += memory_converted
    # for each deployment look for the corresponding hpa (same name) and get: min replicas, max replicas, target cpu utilization, current cpu utilization
    try:
      hpas = self.dynamic_client.resources.get(api_version='autoscaling/v1', kind='HorizontalPodAutoscaler')
      target_hpa = hpas.get(namespace=namespace)
      if target_hpa.items:
        for hpa in target_hpa.items:
          if hpa.metadata.name == deployment.metadata.name:
            hpa_max = hpa.spec.maxReplicas
            hpa_min = hpa.spec.minReplicas
            target_cpu = hpa.spec.targetCPUUtilizationPercentage
            current_cpu = hpa.status.currentCPUUtilizationPercentage
    except ApiException as error:
      print(error)
    # print these info in a csv using the function below
    self.build_csv(outputfile, namespace, deployment.metadata.name, replicas, limits, requests, hpa_max, hpa_min, target_cpu, current_cpu, max_surge)

  def build_csv(self, outputfile, namespace, deployment_name, replicas, limits, requests, hpa_max, hpa_min, target_cpu, current_cpu, max_surge):
    # write a new row in a csv containing the specified info
    fields = [namespace,deployment_name,replicas,limits[0],limits[1],requests[0],requests[1],hpa_max,hpa_min,target_cpu,current_cpu,max_surge]
    with open(r'output.csv', 'a') as outputfile:
      writer = csv.writer(outputfile)
      writer.writerow(fields)
    outputfile.close()
    # get the service associated to the deployment?

  def init_csv(self):
    fields = ['Namespace','Application','Replicas','CPU Limits','Memory Limits','CPU Requests','Memory Requests','HPA Max','HPA Min','Target CPU utilization','Current CPU Utilization','Max Surge']
    with open(r'output.csv', 'a') as outputfile:
      writer = csv.writer(outputfile)
      writer.writerow(fields)
    outputfile.close()

  def convert_cpu_value(value):
    new_value = 0
    number = re.findall(r'\d+',value)
    if value.isdigit():
      if len(value) == 1:
        new_value = number*1000
      else:
        new_value = number
    return new_value

  def convert_memory_value(value):
    new_value = 0
    number = re.findall(r'\d+',value)
    if value.isdigit():
      if len(value) == 1:
        new_value = number*1024
      else:
        new_value = number
    return new_value

if __name__ == '__main__':

  API_URL = os.getenv('API_URL')
  USER = os.getenv('USER')
  # PWD = os.getenv('PWD')
  PWD = getpass("Password: ")

  re = ResourceEvaluator(USER, PWD, API_URL)

  re.init_csv()
  re.get_ns()
  re.get_deployments()
  for deployment in re.deployments:
    re.get_resources_info(deployment.metadata.namespace, deployment, 'output.csv')
