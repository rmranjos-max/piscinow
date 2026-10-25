# Piscinow — Etapa 4: ambiente das lojas e matching

**Data:** 2026-10-25
**Status:** aprovado pelo usuário em conversa ("segue")
**Origem:** PRD v2.0, RF-02 (matching determinístico com justificativa auditável) e regra de privacidade (loja recebe só dados autorizados). Fatias 1.2 e 1.4 da Fase 1.
**Fora desta etapa:** propostas, negociação, liberação de contato (Etapa 5); matching de instaladores (Etapa 6); envio automático; IA decidindo elegibilidade.

## Objetivo

Depois que existe uma oportunidade qualificada, a equipe executa um matching que diz, loja por loja, se ela pode atender e por quê, revisa o resultado, encaminha às lojas elegíveis, e cada loja recebe o briefing **anônimo** numa caixa de entrada onde responde se tem interesse.

## Regras de negócio

1. **Perfil de atendimento** de cada loja é mantido **só pelo admin** no piloto: cidades atendidas, tipos de piscina (fibra, vinil, alvenaria), faixas de orçamento (as mesmas do briefing), capacidade (oportunidades abertas ao mesmo tempo) e ativo/inativo. Loja sem perfil é inelegível ("sem perfil de atendimento").
2. **Matching é determinístico.** Critérios, todos registrados por loja: aprovada, perfil ativo, cidade atendida, tipo de piscina, faixa de orçamento, capacidade livre. A IA não participa.
3. **Cidade:** comparação sem acento e sem maiúsculas; a cidade atendida precisa aparecer como palavra inteira na localização do comprador ("Valinhos, SP" casa com "valinhos").
4. **Dados ausentes não eliminam:** tipo "ainda não sei" e orçamento "não informado" (ou ausente) passam nesses critérios, e a justificativa diz isso.
5. **Capacidade:** conta as indicações já encaminhadas àquela loja e ainda não recusadas, em oportunidades ativas.
6. **Toda loja aprovada é avaliada**, elegível ou não; o registro das inelegíveis, com os critérios que falharam, é parte da auditoria.
7. **Revisão do admin:** pode incluir uma loja inelegível ou excluir uma elegível, sempre com **motivo obrigatório**; o override fica registrado (quem, quando, motivo) e não apaga o resultado original.
8. **Encaminhamento é manual** no piloto: "Executar matching" leva a oportunidade a `matched`; "Encaminhar às lojas" grava a data de compartilhamento, leva a `partner_review` e só então a loja enxerga. Executar o matching de novo antes do encaminhamento refaz a avaliação mantendo os overrides.
9. **A loja vê somente** oportunidades encaminhadas a ela, cuja oportunidade segue ativa e cujo comprador mantém a autorização. Retirar a autorização cancela a oportunidade (Etapa 3) e a oportunidade some da caixa.
10. **A loja nunca vê** nome, e-mail, telefone nem o endereço do comprador: usa a projeção `partner_briefing`. Resposta da loja: "Vou analisar" ou "Não tenho interesse" (motivo obrigatório); registra data.
11. Cada passo grava evento no histórico da oportunidade.

## Dados (migration `0003`)

- `partner_profiles`: `member_id` único, `service_areas` (JSONB lista de textos), `pool_types` (JSONB lista), `budget_bands` (JSONB lista), `capacity` (inteiro ≥ 1), `active`, `updated_at`, `updated_by`.
- `matching_decisions`: `deal_id` + `partner_member_id` único; `eligible` (resultado do sistema), `criteria` (JSONB lista de `{key, label, passed, detail}`), `override` (`nenhum`, `incluida`, `excluida`), `override_reason`, `override_by`, `override_at`, `shared_at`, `response` (`pendente`, `em_analise`, `recusada`), `response_reason`, `responded_at`, `created_at`, `updated_at`. Loja **efetiva** = (`eligible` e override ≠ `excluida`) ou override = `incluida`.

## Telas

- **Admin, loja:** em `/admin/lojas`, link "Atendimento" por loja leva a um formulário do perfil.
- **Admin, oportunidade:** o detalhe ganha o bloco "Matching": botão executar, tabela de lojas com resultado e critérios (justificativa), ação de incluir/excluir com motivo, botão encaminhar, e a resposta de cada loja.
- **Loja:** item "Oportunidades" no menu; lista das encaminhadas com o briefing anônimo; botões de resposta.

## Entrega em três partes, cada uma com CI verde

- **4a** Modelos, migration e regras puras do matching.
- **4b** Perfil de atendimento e matching no painel do admin.
- **4c** Caixa de entrada da loja, resposta, isolamento entre lojas, capturas e relatório.

## Testes

Regras do matching sem banco (cada critério, ausências, cidade por palavra inteira, capacidade). Banco na CI: restrições, overrides, visibilidade, vazamento entre lojas e de dados de contato, retirada de autorização.

## Limitações assumidas

Casamento de cidade é textual (sem normalizar variações como "Sampa"); no piloto o admin corrige pelo override. Capacidade é um número simples, sem calendário. O comprador não é avisado ainda de que lojas receberam o briefing (notificações ficam para a Etapa 7).
