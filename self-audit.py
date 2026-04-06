#!/usr/bin/env python3
"""
Ecommerce API - Production Readiness Audit
Run this to check your project against production standards
"""

import os
import sys
import json
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple

@dataclass
class CheckResult:
    category: str
    item: str
    status: str  # "PASS", "FAIL", "WARNING", "INFO"
    message: str
    file_path: str = ""

class ProductionAuditor:
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.results: List[CheckResult] = []
        self.score = 0
        self.total = 0
        
    def check(self) -> None:
        """Run all checks"""
        print("🔍 Production Readiness Audit")
        print("=" * 70)
        print(f"Project: {self.project_path.absolute()}\\n")
        
        self._check_application()
        self._check_kubernetes()
        self._check_security()
        self._check_observability()
        self._check_operations()
        self._check_documentation()
        
        self._print_summary()
        
    def _add_result(self, category: str, item: str, status: str, message: str, file_path: str = ""):
        self.results.append(CheckResult(category, item, status, message, file_path))
        self.total += 1
        if status == "PASS":
            self.score += 1
        elif status == "WARNING":
            self.score += 0.5
            
    def _check_application(self) -> None:
        """Check application code quality"""
        print("📦 Checking Application...")
        
        # Check main.py exists
        main_py = self.project_path / "main.py"
        if not main_py.exists():
            self._add_result("Application", "main.py exists", "FAIL", 
                           "main.py not found in project root")
            return
            
        content = main_py.read_text()
        
        # Check connection pooling
        if "ThreadedConnectionPool" in content or "pool" in content.lower():
            self._add_result("Application", "Connection pooling", "PASS", 
                           "Uses connection pooling")
        else:
            self._add_result("Application", "Connection pooling", "FAIL", 
                           "No connection pooling detected - add psycopg2.pool")
            
        # Check for hardcoded secrets
        if re.search(r'password\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE):
            self._add_result("Application", "No hardcoded secrets", "FAIL", 
                           "Hardcoded password found - use environment variables")
        else:
            self._add_result("Application", "No hardcoded secrets", "PASS", 
                           "No hardcoded passwords detected")
            
        # Check structured logging
        if "json.dumps" in content or "logging" in content:
            self._add_result("Application", "Structured logging", "PASS", 
                           "Structured logging detected")
        else:
            self._add_result("Application", "Structured logging", "WARNING", 
                           "Consider adding structured JSON logging")
            
        # Check Prometheus metrics
        if "prometheus_client" in content or "/metrics" in content:
            self._add_result("Application", "Prometheus metrics", "PASS", 
                           "Prometheus metrics endpoint found")
        else:
            self._add_result("Application", "Prometheus metrics", "FAIL", 
                           "Add prometheus-client for /metrics endpoint")
            
        # Check rate limiting
        if "limiter" in content.lower() or "rate" in content.lower():
            self._add_result("Application", "Rate limiting", "PASS", 
                           "Rate limiting detected")
        else:
            self._add_result("Application", "Rate limiting", "WARNING", 
                           "Consider adding flask-limiter for rate limiting")
            
        # Check health probes
        if "/health" in content:
            self._add_result("Application", "Health endpoint", "PASS", 
                           "/health endpoint found")
        else:
            self._add_result("Application", "Health endpoint", "FAIL", 
                           "Add /health endpoint for liveness probes")
            
        if "/ready" in content:
            self._add_result("Application", "Readiness endpoint", "PASS", 
                           "/ready endpoint found")
        else:
            self._add_result("Application", "Readiness endpoint", "FAIL", 
                           "Add /ready endpoint for readiness probes")
            
        print()
        
    def _check_kubernetes(self) -> None:
        """Check Kubernetes manifests"""
        print("☸️  Checking Kubernetes...")
        
        k8s_dir = self.project_path / "k8s"
        if not k8s_dir.exists():
            self._add_result("Kubernetes", "k8s/ directory", "FAIL", 
                           "No k8s/ directory found")
            return
            
        # Find all YAML files
        yaml_files = list(k8s_dir.rglob("*.yaml")) + list(k8s_dir.rglob("*.yml"))
        
        if not yaml_files:
            self._add_result("Kubernetes", "YAML manifests", "FAIL", 
                           "No YAML files in k8s/")
            return
            
        all_content = "\\n".join([f.read_text() for f in yaml_files])
        
        # Check security contexts
        if "runAsNonRoot" in all_content or "runAsUser" in all_content:
            self._add_result("Kubernetes", "Security contexts", "PASS", 
                           "Pod security contexts configured")
        else:
            self._add_result("Kubernetes", "Security contexts", "FAIL", 
                           "Add securityContext (runAsNonRoot: true)")
            
        # Check resource limits
        if "resources:" in all_content and "limits:" in all_content:
            self._add_result("Kubernetes", "Resource limits", "PASS", 
                           "Resource limits and requests set")
        else:
            self._add_result("Kubernetes", "Resource limits", "WARNING", 
                           "Add resource requests/limits to containers")
            
        # Check probes
        if "livenessProbe" in all_content:
            self._add_result("Kubernetes", "Liveness probe", "PASS", 
                           "Liveness probe configured")
        else:
            self._add_result("Kubernetes", "Liveness probe", "FAIL", 
                           "Add livenessProbe to deployment")
            
        if "readinessProbe" in all_content:
            self._add_result("Kubernetes", "Readiness probe", "PASS", 
                           "Readiness probe configured")
        else:
            self._add_result("Kubernetes", "Readiness probe", "FAIL", 
                           "Add readinessProbe to deployment")
            
        # Check network policies
        if "NetworkPolicy" in all_content:
            self._add_result("Kubernetes", "Network policies", "PASS", 
                           "NetworkPolicy found")
        else:
            self._add_result("Kubernetes", "Network policies", "WARNING", 
                           "Add NetworkPolicy for zero-trust networking")
            
        # Check HPA
        if "HorizontalPodAutoscaler" in all_content or "hpa" in all_content.lower():
            self._add_result("Kubernetes", "Auto-scaling", "PASS", 
                           "HPA configured")
        else:
            self._add_result("Kubernetes", "Auto-scaling", "INFO", 
                           "Consider adding HorizontalPodAutoscaler")
            
        print()
        
    def _check_security(self) -> None:
        """Check security configurations"""
        print("🔒 Checking Security...")
        
        dockerfile = self.project_path / "Dockerfile"
        if dockerfile.exists():
            content = dockerfile.read_text()
            
            if "USER" in content:
                self._add_result("Security", "Non-root container", "PASS", 
                               "Dockerfile uses non-root USER")
            else:
                self._add_result("Security", "Non-root container", "FAIL", 
                               "Add 'USER' instruction to Dockerfile")
                
        # Check for .gitignore
        gitignore = self.project_path / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if "venv" in content and ".env" in content:
                self._add_result("Security", ".gitignore", "PASS", 
                               ".gitignore properly configured")
            else:
                self._add_result("Security", ".gitignore", "WARNING", 
                               "Add venv/ and .env to .gitignore")
        else:
            self._add_result("Security", ".gitignore", "FAIL", 
                           "No .gitignore file found")
            
        print()
        
    def _check_observability(self) -> None:
        """Check monitoring and logging"""
        print("📊 Checking Observability...")
        
        # Check if prometheus metrics endpoint exists
        main_py = self.project_path / "main.py"
        if main_py.exists():
            content = main_py.read_text()
            
            if "/metrics" in content:
                self._add_result("Observability", "Metrics endpoint", "PASS", 
                               "/metrics endpoint implemented")
            else:
                self._add_result("Observability", "Metrics endpoint", "FAIL", 
                               "Add /metrics endpoint for Prometheus")
                
        print()
        
    def _check_operations(self) -> None:
        """Check operational tooling"""
        print("🔧 Checking Operations...")
        
        # Check Makefile
        makefile = self.project_path / "Makefile"
        if makefile.exists():
            self._add_result("Operations", "Makefile", "PASS", 
                           "Makefile found for automation")
        else:
            self._add_result("Operations", "Makefile", "FAIL", 
                           "Create Makefile for common operations")
            
        # Check CI/CD
        github_dir = self.project_path / ".github" / "workflows"
        if github_dir.exists() and any(github_dir.iterdir()):
            self._add_result("Operations", "CI/CD", "PASS", 
                           "GitHub Actions workflows found")
        else:
            self._add_result("Operations", "CI/CD", "WARNING", 
                           "Consider adding GitHub Actions for CI/CD")
            
        print()
        
    def _check_documentation(self) -> None:
        """Check documentation"""
        print("📚 Checking Documentation...")
        
        readme = self.project_path / "README.md"
        if readme.exists():
            content = readme.read_text()
            size = len(content)
            
            if size > 2000:
                self._add_result("Documentation", "README.md", "PASS", 
                               f"Comprehensive README ({size} chars)")
            elif size > 500:
                self._add_result("Documentation", "README.md", "WARNING", 
                               f"README could be more detailed ({size} chars)")
            else:
                self._add_result("Documentation", "README.md", "FAIL", 
                               f"README too short ({size} chars)")
        else:
            self._add_result("Documentation", "README.md", "FAIL", 
                           "No README.md found")
            
        # Check for runbook
        runbook = self.project_path / "RUNBOOK.md"
        if runbook.exists():
            self._add_result("Documentation", "Runbook", "PASS", 
                           "Operations runbook found")
        else:
            self._add_result("Documentation", "Runbook", "INFO", 
                           "Consider adding RUNBOOK.md for operations")
            
        print()
        
    def _print_summary(self) -> None:
        """Print audit summary"""
        print("=" * 70)
        print("📋 AUDIT SUMMARY")
        print("=" * 70)
        
        # Group by category
        categories = {}
        for result in self.results:
            if result.category not in categories:
                categories[result.category] = []
            categories[result.category].append(result)
            
        # Print by category
        for category, items in categories.items():
            print(f"\\n{category}:")
            for item in items:
                icon = "✅" if item.status == "PASS" else "⚠️" if item.status == "WARNING" else "❌" if item.status == "FAIL" else "ℹ️"
                print(f"  {icon} {item.item}: {item.message}")
                
        # Calculate score
        percentage = (self.score / self.total * 100) if self.total > 0 else 0
        
        print("\\n" + "=" * 70)
        print(f"📊 SCORE: {self.score:.1f}/{self.total} ({percentage:.0f}%)")
        print("=" * 70)
        
        # Recommendations
        if percentage >= 90:
            print("🌟 EXCELLENT: Production-ready project!")
        elif percentage >= 70:
            print("✅ GOOD: Minor improvements needed")
        elif percentage >= 50:
            print("⚠️  FAIR: Several items need attention")
        else:
            print("❌ NEEDS WORK: Significant improvements required")
            
        # Critical fixes
        critical = [r for r in self.results if r.status == "FAIL"]
        if critical:
            print("\\n🔴 CRITICAL FIXES NEEDED:")
            for item in critical[:5]:
                print(f"   - {item.category}/{item.item}: {item.message}")
                
        # Export to JSON
        export_path = self.project_path / "audit-results.json"
        with open(export_path, 'w') as f:
            json.dump({
                "score": self.score,
                "total": self.total,
                "percentage": percentage,
                "results": [asdict(r) for r in self.results]
            }, f, indent=2)
        print(f"\\n📄 Detailed results saved to: {export_path}")

def main():
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."
    auditor = ProductionAuditor(project_path)
    auditor.check()

if __name__ == "__main__":
    main()