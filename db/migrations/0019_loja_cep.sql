-- 0019_loja_cep.sql — cadastro de loja começa pelo CEP.
-- O painel preenche endereço/município/UF e coordenadas a partir do CEP
-- (BrasilAPI/ViaCEP + geocodificação OpenStreetMap com o número).

ALTER TABLE loja ADD COLUMN cep text;
ALTER TABLE loja ADD COLUMN numero text;
