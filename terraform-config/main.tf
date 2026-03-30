terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }
}

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "minikube"
}

provider "helm" {
  kubernetes {
    config_path    = "~/.kube/config"
    config_context = "minikube"
  }
}

# Namespace for our application
resource "kubernetes_namespace" "ecommerce" {
  metadata {
    name = "ecommerce"
  }
}

# PostgreSQL using Helm (Bitnami chart) - FIXED CONFIGURATION
resource "helm_release" "postgres" {
  name       = "ecommerce-db"
  repository = "https://charts.bitnami.com/bitnami"
  chart      = "postgresql"
  version    = "15.5.0"
  namespace  = kubernetes_namespace.ecommerce.metadata[0].name
  
  # CRITICAL FIXES:
  timeout        = 300           # 5 minutes is enough if image is valid
  wait           = false         # Don't wait forever (atomic = false)
  atomic         = false         # Don't rollback on failure (lets you debug)
  recreate_pods  = true          # Force recreate on upgrade
  
  # CRITICAL: Use legacy repository since Bitnami deprecated free images
  set {
    name  = "image.registry"
    value = "docker.io"
  }
  
  set {
    name  = "image.repository"
    value = "bitnamilegacy/postgresql"
  }
  
  set {
    name  = "image.tag"
    value = "16.3.0-debian-12-r10"  # This exists in legacy repo
  }

  set {
    name  = "auth.username"
    value = "ecommerce"
  }
  
  set {
    name  = "auth.password"
    value = "devops123"
  }
  
  set {
    name  = "auth.database"
    value = "ecommerce"
  }

  set {
    name  = "primary.persistence.size"
    value = "5Gi"
  }
  
  # Disable persistence for testing (optional - remove if you need data)
  # set {
  #   name  = "primary.persistence.enabled"
  #   value = "false"
  # }

  depends_on = [kubernetes_namespace.ecommerce]
}

resource "kubernetes_config_map" "app_code" {
  metadata {
    name      = "app-code"
    namespace = kubernetes_namespace.ecommerce.metadata[0].name
  }

  binary_data = {
    "main.py" = filebase64("${path.module}/app/main.py")
  }
}

# Store connection info as Kubernetes secret for apps
resource "kubernetes_secret" "db_credentials" {
  metadata {
    name      = "db-credentials"
    namespace = kubernetes_namespace.ecommerce.metadata[0].name
  }

  data = {
    host     = "ecommerce-db-postgresql"
    port     = "5432"
    username = "ecommerce"
    password = "devops123"
    database = "ecommerce"
  }
  
  depends_on = [helm_release.postgres]
}