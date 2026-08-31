# Tech Stack Guide — organization's approved tools per layer

> Status: living reference, distilled from the organization's architecture standards.
> Human- and agent-readable on purpose.

## Why this exists

Conception Step 4 ("Tech stack") and its "Gerar com agente" button ground technology
choices in tools the organization has actually adopted and can support. `tech_stack_options`
(`backend/app/db/models/system_scope.py`) is the closed catalog picked from in the UI.

## Layers and Technologies Catalog

| Layer | Technology |
|---|---|
| **Frontend** | React + TypeScript + Vite + Tailwind CSS + shadcn/ui |
|  | React + TypeScript + Vite + MUI |
|  | React + TypeScript + Vite + Ant Design |
|  | React + TypeScript + Vite + PrimeReact |
|  | Next.js + TypeScript + Tailwind CSS + shadcn/ui |
|  | Vue 3 + TypeScript + Vite + Tailwind CSS |
|  | Nuxt + TypeScript + Tailwind CSS |
|  | Angular + TypeScript + Angular Material |
|  | Astro + TypeScript + Tailwind CSS |
|  | HTML + CSS + JavaScript |
| **Mobile** | React Native + Expo + TypeScript + NativeWind |
|  | React Native + Expo + Tamagui |
|  | Flutter + Dart |
| **Backend** | Python + FastAPI + SQLAlchemy async |
|  | Python + FastAPI + SQLModel |
|  | Node.js + TypeScript + NestJS |
|  | Node.js + TypeScript + Fastify |
|  | Node.js + TypeScript + Express |
|  | C# + ASP.NET Core Web API |
|  | Java + Spring Boot |
| **Database** | PostgreSQL |
|  | MySQL |
|  | SQL Server |
|  | MongoDB |
|  | SQLite |
|  | DynamoDB |
| **Cache** | Redis |
|  | Valkey |
| **Messaging / Event Bus** | RabbitMQ |
|  | Apache Kafka |
|  | AWS SQS + SNS |
|  | Azure Service Bus |
| **Authentication / Identity** | Keycloak |
|  | Auth0 |
|  | Microsoft Entra ID |
|  | AWS Cognito |
|  | Clerk |
|  | Supabase Auth |
| **Storage** | AWS S3 |
|  | Azure Blob Storage |
|  | Google Cloud Storage |
|  | MinIO |
| **Search** | Elasticsearch |
|  | OpenSearch |
|  | Meilisearch |
| **API / Gateway** | REST API |
|  | GraphQL |
|  | gRPC |
|  | Kong Gateway |
|  | AWS API Gateway |
| **Deploy / Infrastructure** | Docker |
|  | Docker Compose |
|  | Kubernetes |
|  | Helm |
|  | Terraform |
|  | AWS ECS / Fargate |
|  | AWS EKS |
|  | Azure Container Apps |
|  | Azure AKS |
|  | Vercel |
|  | Cloudflare Pages |
| **CI/CD** | GitHub Actions |
|  | GitLab CI/CD |
|  | Azure DevOps Pipelines |
|  | Jenkins |
| **Observability** | OpenTelemetry |
|  | Prometheus + Grafana |
|  | Grafana Loki |
|  | Datadog |
|  | Sentry |
| **Testing** | Vitest + Testing Library |
|  | Jest + Testing Library |
|  | Playwright |
|  | Cypress |
|  | Pytest |
|  | xUnit |
| **Documentation** | OpenAPI / Swagger |
|  | Storybook |
|  | Docusaurus |
