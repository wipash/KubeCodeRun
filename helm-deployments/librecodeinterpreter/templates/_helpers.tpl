{{/*
Expand the name of the chart.
*/}}
{{- define "librecodeinterpreter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "librecodeinterpreter.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "librecodeinterpreter.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "librecodeinterpreter.labels" -}}
helm.sh/chart: {{ include "librecodeinterpreter.chart" . }}
{{ include "librecodeinterpreter.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "librecodeinterpreter.selectorLabels" -}}
app.kubernetes.io/name: {{ include "librecodeinterpreter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use for API
*/}}
{{- define "librecodeinterpreter.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "librecodeinterpreter.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the executor service account
*/}}
{{- define "librecodeinterpreter.executorServiceAccountName" -}}
{{- if .Values.execution.serviceAccount.create }}
{{- default (printf "%s-executor" (include "librecodeinterpreter.fullname" .)) .Values.execution.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.execution.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Execution namespace
*/}}
{{- define "librecodeinterpreter.executionNamespace" -}}
{{- default .Release.Namespace .Values.execution.namespace }}
{{- end }}

{{/*
Redis URL
*/}}
{{- define "librecodeinterpreter.redisUrl" -}}
{{- if .Values.redis.url }}
{{- .Values.redis.url }}
{{- else if .Values.redis.host }}
{{- if .Values.redis.password }}
{{- printf "redis://:%s@%s:%d/%d" .Values.redis.password .Values.redis.host (int .Values.redis.port) (int .Values.redis.db) }}
{{- else }}
{{- printf "redis://%s:%d/%d" .Values.redis.host (int .Values.redis.port) (int .Values.redis.db) }}
{{- end }}
{{- else }}
{{- "redis://redis:6379/0" }}
{{- end }}
{{- end }}

{{/*
Check if Helm-managed secret is needed
Returns true if any of the following conditions are met:
- api.existingSecret is not set (API_KEY will be auto-generated)
- redis.existingSecret is not set (REDIS_URL needs to be generated)
- minio.existingSecret is not set AND minio.useIAM is false (S3 credentials needed)
*/}}
{{- define "librecodeinterpreter.needsHelmSecret" -}}
{{- if or (not .Values.api.existingSecret) (not .Values.redis.existingSecret) (and (not .Values.minio.existingSecret) (not .Values.minio.useIAM)) }}
{{- true }}
{{- end }}
{{- end }}

{{/*
Validate MinIO/S3 configuration
When not using existingSecret or IAM, accessKey and secretKey must be provided.
*/}}
{{- define "librecodeinterpreter.validateMinioConfig" -}}
{{- if and (not .Values.minio.existingSecret) (not .Values.minio.useIAM) }}
{{- if or (not .Values.minio.accessKey) (not .Values.minio.secretKey) }}
{{- fail "minio.accessKey and minio.secretKey are required when not using existingSecret or IAM" -}}
{{- end }}
{{- end }}
{{- end }}
