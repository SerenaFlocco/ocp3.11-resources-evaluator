import os
from kubernetes import client
# from kubernetes.client.rest import ApiException
from openshift.dynamic import DynamicClient
from openshift.helper.userpassauth import OCPLoginConfiguration
#from requests.packages.urllib3.exceptions import InsecureRequestWarning
import csv

class ResourceEvaluator:
  
  def __init__(self, user, pwd, apiURL):
    
    self.user = user
    self.pwd = pwd
    self.apiURL = apiURL
    self.acronyms = self.get_acronyms('acronyms.txt')
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
      self.acronyms = [line.rstrip() for line in file]

  def get_ns(self):
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
      target_deployments = deployments.get(namespace=project)
      target_dc = deployment_configs.get(namespace=project)
      # target_sts = stateful_sets.get(namespace=project)
      # target_rs = replica_sets.get(namespace=project)
      if len(target_deployments):
        self.deployments.extend(target_deployments.items)
      if len(target_dc):
        self.deployments.extend(target_dc.items)
      # if len(target_sts):
      #   self.deployments.extend(target_sts.items)
      # if len(target_rs):
      #   self.deployments.extend(target_rs.items)


  def get_resources_info(self, namespace, deployment, outputfile):
    # for each deployment in a namespace collect: replicas, resource limits and requests, hpa max and min, maxSurge
    # if limits and requests are not specified, get the limits resource in the namespace --> limit range default (=limits) and default requests (=requests)
    replicas = deployment.spec.replicas
    max_surge = deployment.spec.rollingParams.maxSurge
    requests = []
    limits = []
    hpa_max = 0
    hpa_min = 0
    target_cpu = 0
    current_cpu = 0
    resources = self.dynamic_client.resources.get(api_version='core/v1', kind='LimitRange')
    target_resources = resources.get(namespace=namespace)
    requests.extend(target_resources.spec.limits[1].defaultRequest)
    limits.extend(target_resources.spec.limits[1].default)
    if deployment.spec.containers[0].resources:
      if deployment.spec.containers[0].resources.requests:
          if deployment.spec.containers[0].resources.requests.cpu:
            requests[0] = deployment.spec.containers[0].resources.requests.cpu
          if deployment.spec.containers[0].resources.requests.memory:
            requests[1] = deployment.spec.containers[0].resources.requests.memory
      if deployment.spec.containers[0].resources.limits:
        if deployment.spec.containers[0].resources.limits.cpu:
          limits[0] = deployment.spec.containers[0].resources.limits.cpu
        if deployment.spec.containers[0].resources.limits.memory:
          limits[1] = deployment.spec.containers[0].resources.limits.memory
    # for each deployment look for the corresponding hpa (same name) and get: min replicas, max replicas, target cpu utilization, current cpu utilization
    hpas = self.dynamic_client.resources.get(api_version='autoscaling/v1', kind='HorizontalPodAutoscaler')
    target_hpa = hpas.get(namespace=namespace,name=deployment.metadata.name)
    if target_hpa:
      hpa_max = target_hpa.spec.maxReplicas
      hpa_min = target_hpa.spec.minReplicas
      target_cpu = target_hpa.spec.targetCPUUtilizationPercentage
      current_cpu = target_hpa.status.currentCPUUtilizationPercentage
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

if __name__ == '__main__':

  API_URL = os.getenv('API_URL')
  USER = os.getenv('USER')
  PWD = os.getenv('PWD')

  re = ResourceEvaluator(API_URL, USER, PWD)

  re.init_csv()
  re.get_ns()
  re.get_deployments()
  for deployment in re.deployments:
    re.get_resources_info(deployment.metadata.namespace, deployment, 'output.csv')