-- 0004_calendar.sql — Dimensão de Calendário DUPLO (global, compartilhada)
-- Civil (dinheiro: mes/ano-calendario) + Varejo (demanda: semana ISO alinhada).
-- Cada dia carrega as chaves dos dois calendarios. Ver PLANO.md 3.12.
-- Preenchida por boardos/calendar_gen.py (nao por SQL) para clareza.

CREATE TABLE dim_calendario (
  data                 date PRIMARY KEY,
  -- civil
  ano_civil            int  NOT NULL,
  mes_civil            int  NOT NULL,
  dia_mes              int  NOT NULL,
  -- dia da semana
  dow_iso              int  NOT NULL,          -- 1=segunda ... 7=domingo (ISO)
  dow_label            text NOT NULL,          -- seg|ter|qua|qui|sex|sab|dom
  is_fim_semana        boolean NOT NULL,
  is_util              boolean NOT NULL,
  is_periodo_pagamento boolean NOT NULL DEFAULT false,  -- inicio/fim de mes
  feriado              boolean NOT NULL DEFAULT false,   -- populado por cadastro de feriados
  -- varejo (ISO week como default; retail_* permite 4-4-5 no futuro)
  iso_year             int  NOT NULL,
  iso_week             int  NOT NULL,
  retail_year          int  NOT NULL,          -- = iso_year no v0
  retail_week          int  NOT NULL,          -- = iso_week no v0
  retail_period        int,                    -- periodo 4-4-5 (opcional/futuro)
  semana_partida       boolean NOT NULL DEFAULT false,   -- semana cruza 2 meses civis
  -- ajuste de composicao de calendario (trading-day)
  qtd_mesmo_dow_no_mes int NOT NULL            -- quantos deste dia-da-semana ha no mes civil
);

CREATE INDEX dim_cal_civil_ix  ON dim_calendario (ano_civil, mes_civil);
CREATE INDEX dim_cal_varejo_ix ON dim_calendario (retail_year, retail_week);

-- Composicao de dias da semana por mes civil (base do ajuste trading-day):
-- quantos sabados, domingos, etc. cada mes tem.
CREATE VIEW v_composicao_mes AS
SELECT ano_civil, mes_civil, dow_iso, dow_label, count(*) AS qtd
FROM dim_calendario
GROUP BY ano_civil, mes_civil, dow_iso, dow_label;
