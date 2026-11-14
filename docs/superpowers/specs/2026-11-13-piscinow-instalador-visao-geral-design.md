# Piscinow — Etapa 6: instalador e administrador

**Data:** 2026-11-13
**Status:** aprovado pelo usuário ("1 e 2 - aceito sua sugestão").
**Origem:** PRD v2.0 (papéis, D4, RF-03 funil, governança). Protótipo v3 (menus de instalador e administrador).
**Fora desta etapa:** acompanhamento da obra, evidências e fotos (Etapa 7), pagamento e repasse a instalador, matching automático de instaladores, notificações.

## Decisões do usuário

1. **O instalador vê o contato do comprador somente depois de aceitar a instalação.**
2. **O instalador tem perfil de atendimento (cidades e tipos de serviço), mantido só pelo admin, como apoio:** o formulário de atribuição destaca quem atende a cidade, mas o sistema não filtra nem decide sozinho.

## Regras de negócio

1. **Atribuição manual.** Só o admin atribui um instalador, e só a uma oportunidade **aceita** (`accepted`). O motivo é obrigatório e fica registrado (quem, quando, motivo). O instalador precisa ser um prestador aprovado.
2. **Uma atribuição ativa por oportunidade** (`pendente` ou `aceita`), garantida por índice parcial no banco. Reatribuir cancela a anterior (`cancelada`) com motivo e cria a nova.
3. **Resposta do instalador:** "Aceito" ou "Não posso" (motivo obrigatório). Aceite é definitivo nesta etapa. Recusa deixa a oportunidade sem instalador e avisa o admin na lista.
4. **O que o instalador vê:** o projeto sem identificação pessoal (código do cliente, briefing anônimo), a cidade, a loja responsável, o escopo, as exclusões e o prazo da proposta aceita. **Não vê o preço** da proposta. **Nome, e-mail e telefone do comprador aparecem só depois do aceite da atribuição**, e só para o instalador aceito.
5. **O comprador vê** o instalador identificado (nome) na página de propostas **depois que ele aceitou** a atribuição, não antes.
6. **Perfil do instalador** (admin): cidades atendidas, tipos de serviço (instalação, manutenção, reparo) e ativo. Sem perfil ou inativo, o instalador continua atribuível, mas aparece como "sem perfil" ou "não atende a cidade" no formulário. A cidade usa a mesma regra de palavra inteira do matching das lojas.
7. Um instalador não enxerga atribuições de outro, nem de oportunidades canceladas ou sem aceite.
8. Cada passo gera evento no histórico da oportunidade.
9. **Visão geral** usa só dados reais. Nenhum número de exemplo em produção: onde não há dados, a tela diz isso.

## Dados (migration `0005`)

- `installer_profiles`: `member_id` único, `service_areas` e `service_kinds` (JSONB), `active`, `updated_at`, `updated_by`.
- `installer_assignments`: deal, instalador, status (`pendente`, `aceita`, `recusada`, `cancelada`), motivo e autor da atribuição, data, motivo da resposta e data da resposta, motivo do cancelamento; índice parcial único de uma ativa por deal.

## Telas

- **Instalador:** novo item "Instalações" (primeiro do menu): lista de atribuições, projeto, ações de resposta, e contato após o aceite.
- **Admin, prestadores:** link "Atendimento" por instalador (formulário do perfil).
- **Admin, oportunidade aceita:** bloco "Instalação" com a atribuição atual, formulário de atribuir ou reatribuir (instaladores destacando quem atende a cidade) e a resposta.
- **Admin, Visão geral** (`/admin`, primeiro item do menu): funil por estado, perdas por motivo, pedidos de atenção abertos, fila de admissão, instalações aguardando resposta ou sem instalador, tempo médio entre criação e aceite quando houver oportunidades aceitas.
- **Admin, Governança** (`/admin/governanca`): trilha de auditoria somente de leitura dos eventos de todas as oportunidades, com filtro por tipo (revisões do matching, liberações de contato, perdas, viabilidade, atribuições) e paginação.
- **Comprador:** página de propostas mostra o instalador responsável depois do aceite dele.

## Entrega

- **6a** Dados, regras e serviço de atribuição.
- **6b** Perfil do instalador, atribuição no admin e caixa "Instalações" do instalador, com o comprador vendo o responsável.
- **6c** Visão geral e Governança, capturas e relatório.

## Limitações assumidas

Sem matching automático nem capacidade do instalador; sem calendário; sem fotos ou evidências; sem notificações; o tempo médio é uma média simples, sem distribuição.
