# Deploy no Render (via Blueprint)

O [render.yaml](render.yaml) descreve tudo: um **Postgres com PostGIS** + a **API**.
Deploy automático a cada `git push` na branch `main`.

## Passo a passo (lado do Render)

1. Crie conta em **render.com** e conecte sua conta do GitHub.
2. **New → Blueprint** → selecione o repositório **BoardOsClaude** → **Apply**.
   - O Render lê o `render.yaml`, cria o banco `boardos-db` e o serviço `boardos-api`.
3. No primeiro deploy o `startCommand` roda as migrações (schema + PostGIS + RLS)
   e sobe a API. Acompanhe em **Logs**.
4. Quando o serviço ficar **Live**, teste:
   - Saúde: `https://boardos-api.onrender.com/health` → `{"ok": true, ...}`
   - (a URL exata aparece no painel do serviço)

## Carregar dados de demonstração (opcional)

A API sobe sem dados. No serviço `boardos-api` → **Shell**, rode UM dos seeds:

- **Comparação YoY (recomendado)** — ~3 anos no gold, faz `/comparacao/yoy` responder:
  ```bash
  python scripts/seed_demo_gold.py
  ```
- **Pipeline de item** — cria tenant, calendário e ingere o CSV de exemplo (2 dias):
  ```bash
  python scripts/seed.py
  ```

Ambos imprimem o `tenant=<UUID>`. Depois:
```bash
curl "https://boardos-api.onrender.com/comparacao/yoy?ano=2026&mes=8" \
     -H "X-Tenant-Id: <UUID>"
curl "https://boardos-api.onrender.com/kpi/diario?data_de=2026-08-01&data_ate=2026-08-31" \
     -H "X-Tenant-Id: <UUID>"
```

## Planos e ressalvas

- **Banco:** `basic-256mb` (pago, ~US$6/mês). O Render só permite **um** Postgres
  free por workspace e o free expira em ~30 dias — por isso o banco é pago.
- **Web service:** `free` (dorme após inatividade; primeira chamada demora a
  acordar). Suba para um plano pago quando quiser sem "cold start".
- Se `CREATE EXTENSION postgis` ou `CREATE ROLE` falhar por permissão,
  ajustamos a migração (raro; o owner do Render costuma ter privilégio).

## Sem front-end ainda

Este deploy expõe a **API** (JSON), não um dashboard. O visual continua no
protótipo ([prototipo-painel.html](prototipo-painel.html)). O front-end real é o M2.
