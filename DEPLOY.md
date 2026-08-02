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

A API sobe sem dados. Para ver os endpoints com conteúdo, rode o seed uma vez:

- No serviço `boardos-api` → **Shell** → execute:
  ```bash
  python scripts/seed.py
  ```
  Isso cria o tenant demo, popula o calendário e ingere o CSV de exemplo.
  Anote o `tenant=<UUID>` impresso. Depois:
  ```bash
  curl "https://boardos-api.onrender.com/kpi/diario?data_de=2026-08-01&data_ate=2026-08-31" \
       -H "X-Tenant-Id: <UUID>"
  ```

> O `/comparacao/yoy` precisa de histórico de ~2 anos; o CSV de exemplo tem só
> 2 dias. Para exercitar a comparação no banco, um seed maior (2 anos no grão
> item) entra num passo seguinte.

## Ressalvas do free tier

- O web service **dorme** após inatividade (primeira chamada demora a acordar).
- O Postgres grátis do Render **expira em ~30 dias** — ótimo para testar, não
  para produção.
- Se `CREATE EXTENSION postgis` ou `CREATE ROLE` falhar por permissão no plano,
  ajustamos a migração (é raro; o usuário owner do Render costuma ter privilégio).

## Sem front-end ainda

Este deploy expõe a **API** (JSON), não um dashboard. O visual continua no
protótipo ([prototipo-painel.html](prototipo-painel.html)). O front-end real é o M2.
