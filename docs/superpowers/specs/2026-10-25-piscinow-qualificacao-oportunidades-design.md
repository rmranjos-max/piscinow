# Piscinow — Etapa 3: qualificação comercial e oportunidades

**Data:** 2026-10-25
**Status:** aprovado pelo usuário em conversa (conversa livre com agente vendedor; decisões D1 a D6 do plano de experiência)
**Origem:** PRD v2.0, RF-01 (qualificação assistida por IA) e RF-03 (oportunidade). Fatias 1.1 e 1.3 da Fase 1.
**Fora desta etapa:** caixa de entrada da loja, matching, propostas, viabilidade (Etapas 4 e 5).

## Objetivo

O comprador logado conversa com um **agente vendedor** (assistente virtual da Piscinow), que descobre o que ele quer. Quando há os dados mínimos e o consentimento, nasce uma **oportunidade** que a equipe acompanha no painel.

## Regras de negócio decididas

1. **Transparência.** O agente se apresenta como assistente virtual e, se perguntado, diz que é uma IA. Nunca afirma ser pessoa. A conversa é livre e calorosa, mas nunca enganosa.
2. **Dados mínimos para abrir oportunidade:** localização, tipo de piscina, prazo e consentimento. Dimensões, orçamento, terreno e finalidade são desejáveis, não obrigatórios.
3. **Orçamento:** perguntado até 2 vezes. Na segunda, o agente reforça o valor de informar uma faixa, **sem afirmar que preços vão subir ou mudar**. Depois, "não sei" é aceito e registrado como "não informado". Nunca bloqueia a oportunidade.
4. **Consentimento explícito por botão**, nunca deduzido do texto: "Autorizo compartilhar meu briefing, sem nome e sem contato, com lojas compatíveis" ou "Prefiro conversar antes". Sem consentimento, não nasce oportunidade. A pessoa pode concedê-lo depois, na tela do briefing.
5. **Cada campo** guarda valor, origem (`cliente`, `parceiro`, `admin`), estado de verificação (`declarado`, `verificado`, `pendente`) e data. Correção feita pelo comprador vira origem `cliente`, declarado.
6. **Uma oportunidade ativa por comprador**, garantida por índice parcial único no banco (ativa = não `lost` nem `cancelled`).
7. **A loja nunca vê nome, telefone nem e-mail.** A visão do briefing para parceiros é uma projeção separada, testada contra vazamento. O contato só é liberado após o aceite da proposta (Etapa 5).
8. **Na dúvida o agente não inventa.** Não afirma preço, prazo, disponibilidade, garantia nem condição. Diz que vai confirmar com a equipe e abre um **pedido de atenção** visível ao admin.
9. **Conhecimento aprovado** vem da memória que o admin alimenta em "Ensinar o concierge" (itens `human` têm prioridade).

## Arquitetura do agente

O **código decide o objetivo do turno**; o **modelo decide como dizer**.

1. A cada mensagem do comprador, uma chamada de **extração** devolve JSON com os campos que ele informou (mesmo fora de ordem, vários de uma vez). O código **valida cada campo** (`normalize_field`): enum conhecido ou texto curto. Valor inválido é descartado.
2. O código calcula o **próximo objetivo** (`next_goal`): perguntar um campo obrigatório, perguntar orçamento (tentativa 1 ou 2), pedir consentimento, ou encerrar. Depois de 3 perguntas sem sucesso sobre um campo obrigatório, o objetivo vira **pedido de atenção** à equipe.
3. Uma chamada de **resposta** recebe: persona, regras de proibição, dados já coletados, objetivo do turno e conhecimento aprovado relevante. O modelo escreve a resposta inteira.
4. Uma **barreira de saída** (`check_reply`) rejeita respostas que: citem valor em reais que a pessoa não escreveu; prometam prazo, garantia ou disponibilidade; afirmem que preços vão subir; afirmem ser humano. Rejeitada, regenera (até 2 vezes) e, por fim, usa um texto seguro fixo.
5. Falha do provedor de LLM nunca derruba a tela: o histórico e o briefing continuam visíveis, com uma mensagem de indisponibilidade.

Cada mensagem custa duas chamadas ao modelo. A rota de envio usa o limite de requisições já existente para o chat.

## Dados (novas tabelas, migration `0002`)

- `lead_qualifications`: uma por comprador (`member_id` único). Estado (`em_andamento`, `qualificada`), consentimento (`nao_respondido`, `concedido`, `recusado`) com data, contagem de perguntas por campo (`asks`, JSON), nota de atenção e data.
- `qualification_fields`: um registro por campo (`qualification_id` + `key` único), com valor, origem, verificação, data e quem atualizou.
- `deals`: `number` sequencial (código `OP-0007`), comprador, qualificação, estado, loja atribuída (nula nesta etapa), motivo de perda, datas. Estados já completos para não exigir nova migration: `new, qualified, matched, partner_review, proposal_sent, negotiating, accepted, lost, cancelled`. Nesta etapa só `qualified`, `lost` e `cancelled` são usados.
- `deal_events`: histórico (tipo, estado anterior e novo, nota, autor, data).
- `conversations.purpose`: `landing` (padrão) ou `qualificacao`.

## Telas

- **Comprador:** `Consultor` no menu (entre Início e Explorar). Chat à esquerda; "Seu briefing" à direita com origem de cada campo, correção de campo e o botão de consentimento. Retoma de onde parou. Cada envio é um formulário (sem JavaScript novo).
- **Início:** quando não há qualificação, o próximo passo sugere o consultor; o caminho direto pela vitrine continua disponível.
- **Admin:** `Oportunidades` no menu. Lista com filtro por estado e indicador de pedidos de atenção; detalhe com o briefing completo (inclusive contato), histórico e a ação de **marcar como perdida** (motivo obrigatório).

## Entrega em três partes, cada uma com CI verde

- **3a** Modelos, migration e regras puras: catálogo e validação de campos, próximo objetivo, barreira de saída, projeção do briefing para parceiros.
- **3b** Agente, consultor e painel do briefing.
- **3c** Oportunidades, histórico, painel do admin e integração com o Início. Capturas de tela ao final.

## Testes

Regras puras sem banco (rodam localmente). Agente com provedor roteirizado, incluindo os cenários do PRD (seção 8): preço ausente, catálogo vazio, pergunta fora do escopo, pedido de liberação financeira, vazamento entre contas. Rotas e restrições de banco na CI.

## Limitações assumidas

A naturalidade da conversa depende do modelo real e do prompt, e não pode ser medida com o provedor de teste. O piloto deve rodar com um modelo real e o admin revisar as transcrições.
