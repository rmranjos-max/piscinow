# Piscinow — Etapa 5: propostas, negociação e viabilidade

**Data:** 2026-10-25
**Status:** aprovado pelo usuário ("de acordo"), com as três decisões abaixo nas sugestões propostas.
**Origem:** PRD v2.0, RF-04 (propostas e negociação assistida) e RF-05 (viabilidade simplificada). Fatias 1.5 e 1.6 da Fase 1.
**Fora desta etapa:** fee, pagamento, ligação com Meu projeto/cronograma/pagamento (Etapa 7), notificações, anexos de proposta, IA redigindo proposta.

## Decisões do usuário

1. **Viabilidade trava o aceite quando está pendente ou reprovada.** Só `approved` ou `conditionally_approved` permitem aceitar. O admin preenche o checklist antes.
2. **O fluxo atual de projeto e pagamento não muda.** A proposta aceita fica registrada e visível; a ligação com projeto e cronograma entra na Etapa 7.
3. **Sem ranking nem prioridade.** O comprador compara as propostas das lojas que as enviaram; a loja do sócio não tem tratamento especial.

## Regras de negócio

1. **Quem propõe:** só uma loja a quem a oportunidade foi encaminhada, que ainda a enxerga (efetiva, não recusou, oportunidade ativa, comprador mantém a autorização) e que respondeu "Vou analisar".
2. **Proposta:** itens (descrição e valor `Decimal`, ao menos um), escopo, prazo estimado em dias, validade (data futura) e exclusões. O **total é a soma dos itens**, calculado pelo sistema. Valores positivos, com no máximo duas casas e limite de 99.999.999,99.
3. **Versões imutáveis.** Cada envio cria a versão seguinte (1, 2, 3…) da loja naquela oportunidade; a anterior vira `substituida`. Nenhuma versão é editada depois de enviada. Só existe uma versão `enviada` por loja e oportunidade (índice parcial).
4. **Vigência:** proposta com validade vencida (comparação por data) não pode ser aceita; é exibida como vencida.
5. **Negociação:** o comprador escreve mensagens por loja; a mensagem pode ser marcada como **pedido de revisão**. A loja responde por mensagem ou com nova versão. Cada pedido de revisão leva a oportunidade a `negotiating`; o primeiro envio de proposta leva a `proposal_sent`. Tudo gera evento no histórico.
6. **Recusa pelo comprador** exige motivo e encerra aquela versão (`recusada`); a loja pode enviar uma nova versão enquanto a oportunidade estiver aberta.
7. **Aceite:** o comprador confirma uma versão específica, vigente e a mais recente da loja, e só se a viabilidade estiver `approved` ou `conditionally_approved`. O sistema grava versão, data e termos (a própria versão imutável é o termo), marca a oportunidade `accepted`, atribui a loja, e encerra (`encerrada`) as outras propostas abertas. A decisão é irreversível nesta etapa.
8. **Contato:** o nome, e-mail e telefone do comprador são liberados **somente para a loja atribuída, e somente após o aceite**; o evento `contact_released` fica no histórico. As demais lojas perdem o acesso à oportunidade.
9. **Viabilidade:** checklist fixo (acesso ao imóvel, terreno, escavação, instalações hidráulicas e elétricas, medidas, necessidade de visita), cada item `pendente`, `ok`, `ressalva` ou `impeditivo`, com nota. O resultado (`pending`, `conditionally_approved`, `approved`, `rejected`) é uma **decisão humana do admin**, com responsável e data. `approved` exige todos os itens `ok`; `conditionally_approved` exige nenhum `pendente` nem `impeditivo`; `rejected` exige observação. As ressalvas aparecem para o comprador ao lado da proposta.
10. A loja só enxerga as próprias propostas e mensagens; o comprador só as da própria oportunidade; o admin vê tudo.

## Dados (migration `0004`)

- `proposals` (deal, loja, versão, status `enviada|substituida|recusada|aceita|encerrada`, total, escopo, prazo em dias, validade, exclusões, motivo da decisão, datas, autor), único por (deal, loja, versão); índice parcial único de uma `enviada` por (deal, loja) e de uma `aceita` por deal; checks de total e prazo positivos.
- `proposal_items` (proposta, posição, descrição, valor com check positivo).
- `deal_messages` (deal, loja, autor `comprador|loja`, autor_id, tipo `mensagem|revisao`, texto, data).
- `feasibility_checks` (deal único, itens em JSON, resultado, observações, responsável, data).

## Telas

- **Loja:** na caixa de entrada, "Enviar proposta" (formulário de itens), propostas enviadas por versão, conversa com o comprador.
- **Comprador:** `Propostas` no menu; por loja, a proposta vigente, versões anteriores, ressalvas de viabilidade, conversa, e as ações aceitar (com confirmação explícita), recusar com motivo e pedir revisão. Início ganha o estado.
- **Admin:** no detalhe, bloco "Viabilidade" e as propostas e mensagens de cada loja.

## Entrega

- **5a** Dados e regras puras (valores, vigência, viabilidade) e serviços.
- **5b** Loja: enviar proposta, versões e conversa.
- **5c** Comprador: comparar, revisar, recusar, aceitar; viabilidade no admin; liberação do contato; capturas.

## Limitações assumidas

Sem anexos, sem edição de rascunho (envio é definitivo), sem notificações (cada parte vê a novidade ao abrir a tela), sem ligação com projeto/pagamento, e a validade é por data, não por hora.
