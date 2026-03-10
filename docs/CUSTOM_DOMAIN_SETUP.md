# Custom Domain Setup for API Gateway

Configure `api.meshradar.io` to point to the Mesh Radar WebSocket API Gateway,
so the public repo config uses a clean URL instead of exposing the AWS endpoint.

## Why

The public `meshpoint` repo has `config/default.yaml` with:

```yaml
upstream:
  url: "wss://api.meshradar.io/ws"
```

This avoids exposing your AWS API Gateway ID (`2sm0s2p5ji`) and region in public code.

## Steps

### 1. Request an ACM Certificate

In the AWS Console (us-east-1 region for CloudFront, or your API Gateway region):

```bash
aws acm request-certificate \
  --domain-name "api.meshradar.io" \
  --validation-method DNS \
  --region us-east-1
```

### 2. Validate the Certificate

ACM will give you a CNAME record to add to your DNS. In GoDaddy:

- Go to your meshradar.io DNS settings
- Add a CNAME record with the name and value ACM provides
- Wait for validation (usually 5-30 minutes)

### 3. Create the Custom Domain in API Gateway

For the **WebSocket API** (the one Mesh Points connect to):

```bash
aws apigatewayv2 create-domain-name \
  --domain-name "api.meshradar.io" \
  --domain-name-configurations \
    CertificateArn=arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT_ID
```

### 4. Create the API Mapping

Map the WebSocket API stage to the custom domain:

```bash
aws apigatewayv2 create-api-mapping \
  --domain-name "api.meshradar.io" \
  --api-id YOUR_WEBSOCKET_API_ID \
  --stage prod
```

If you also want the HTTP API on the same domain (e.g., under a path prefix),
create additional mappings with `--api-mapping-key` (e.g., `api` for `/api/*`).

### 5. Add DNS Record in GoDaddy

API Gateway will give you a target domain name (something like
`d-xxxxx.execute-api.us-east-1.amazonaws.com`).

In GoDaddy DNS for meshradar.io:

- Add a **CNAME** record:
  - Name: `api`
  - Value: `d-xxxxx.execute-api.us-east-1.amazonaws.com`
  - TTL: 600

### 6. Verify

```bash
wscat -c wss://api.meshradar.io/ws -H "Authorization: Bearer YOUR_API_KEY"
```

### 7. Update the Private Repo Config

In `config/default.yaml` (private Mesh-Radar repo), update:

```yaml
upstream:
  url: "wss://api.meshradar.io/ws"
```

The old URL (`wss://2sm0s2p5ji.execute-api...`) will continue to work,
but new deployments and the public repo will use the custom domain.

## Notes

- The ACM certificate must be in the same region as the API Gateway
  (us-east-1 for your current setup)
- Custom domains for WebSocket APIs require API Gateway V2
- There is no additional cost for custom domain names in API Gateway
- Consider also setting up `meshradar.io` and `www.meshradar.io` for
  the CloudFront-hosted frontend when you're ready
