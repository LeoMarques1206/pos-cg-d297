# Documentação de Integração Técnica — Output PaperCave para Unity

Esta documentação serve como guia para o programador do Unity (Leo) consumir os dados gerados pela pipeline Python **PaperCave**. 

Para cada paper científico processado, o backend Python gerará uma pasta dedicada em:
`Assets/PaperCaveData/{paper_id}/`

Esta pasta conterá:
1. `manifest.json`: O arquivo JSON contendo os dados estruturados e limpos para a cena.
2. `images/`: Uma pasta contendo todas as figuras extraídas (incluindo imagens compostas fatiadas) no formato `FIG_*.png`.

---

## 1. Estrutura Geral do `manifest.json`

O JSON gerado segue um formato plano (*flat*) otimizado para o parser nativo do Unity (`JsonUtility.FromJson<SceneData>`), eliminando chaves desnecessárias de debug do CrewAI.

```json
{
  "paperTitle": "Título do Artigo Científico",
  "centralContribution": "Descrição geral da contribuição principal",
  "gameObjects": [
    {
      "suggestedName": "Nome do Card",
      "conceptualOrigin": "Seção do paper",
      "category": "abstract | contribution | graphical_representation | image | graph | table",
      "visualMetaphor": "Conteúdo textual puro do card (sem prefixos)",
      "behaviourHint": "Dicas de layout/priority",
      "interactionType": "Click to expand / Drag",
      "whyThisFive": "Justificativa pedagógica",
      "relatedImage": "FIG_1.png",
      "displayType": "text | image | table | graph",
      "rows": 0,
      "columns": 0,
      "tableHeaders": "",
      "tableRows": "",
      "graphLabels": "",
      "graphValues": "",
      "stackIndex": -1
    }
  ]
}
```

---

## 2. As 6 Categorias e Stacks (Decks de Cartas)

O Unity deve criar exatamente **6 áreas/âncoras** na cena (uma para cada categoria). Três delas são cartas individuais e três são pilhas/decks de cartas (Stacks):

### Cartas Individuais (`stackIndex = -1`)
1. **`abstract`** (`displayType: "text"`): Carta contendo o resumo objetivo do paper.
2. **`contribution`** (`displayType: "text"`): A contribuição central do paper. É a única carta com prioridade máxima (`priority="primary"` na hierarquia).
3. **`graphical_representation`** (`displayType: "image"` ou `"text"`): O diagrama visual mais importante do paper (ex: o pipeline geral). A imagem correspondente é salva na pasta `images/` e referenciada em `relatedImage`. **Nota:** Esta figura é excluída do stack de imagens geral para não ficar duplicada.

### Decks/Stacks de Cartas (`stackIndex >= 0`)
4. **`image`** (`displayType: "image"`): Stack contendo as figuras do paper.
5. **`graph`** (`displayType: "graph"`): Stack contendo gráficos do paper.
6. **`table`** (`displayType: "table"`): Stack contendo tabelas do paper.

### Como lidar com Stacks no Unity:
Os itens de um stack vêm desmembrados na lista `gameObjects` com a mesma categoria (ex: `category: "image"`) e um campo `"stackIndex": i` (começando em 0). 
No Unity, o `JsonSceneInstantiator` deve:
1. Agrupar os `gameObjects` que possuem a mesma `category` se `stackIndex` for diferente de -1.
2. Instanciá-los na mesma âncora física correspondente à categoria.
3. Aplicar um offset linear suave (ex: `z += 0.05f * stackIndex`) para que as cartas fiquem empilhadas como um deck.

---

## 3. Tabelas Procedurais Dinâmicas

Quando `displayType` for `"table"`, os dados vêm estruturados e limpos de forma procedural:
* **`tableHeaders`**: As colunas da tabela separadas por pipe `|`.
  * *Exemplo:* `"Modelo | Acurácia | Latência (ms)"`
* **`tableRows`**: As linhas da tabela separadas por ponto e vírgula `;`, com células divididas por pipe `|`.
  * *Exemplo:* `"GPT-4 | 0.92 | 120; GPT-3.5 | 0.84 | 80; Llama-3 | 0.78 | 45"`
* **`rows`** e **`columns`**: Inteiros indicando as dimensões exatas da tabela para o `TableBuilder.cs`.

---

## 4. Gráficos Procedurais Dinâmicos (Novo Recurso)

Atualmente, o `BarChartBuilder.cs` no Unity utiliza dados mockados estáticos de Action Units/expressões faciais. Para permitir gráficos procedurais alimentados pelo JSON do paper, o backend fornece dois novos campos semelhantes à tabela:
* **`graphLabels`**: Rótulos das barras do eixo X separados por pipe `|`.
  * *Exemplo:* `"GPT-4 | GPT-3.5 | Llama-3 | Mistral"`
* **`graphValues`**: Valores numéricos float das barras correspondentes separados por pipe `|`.
  * *Exemplo:* `"0.92 | 0.84 | 0.78 | 0.71"`
  
### Recomendação no Unity:
Ajustar o `BarChartBuilder.cs` para aceitar estes parâmetros no método `Build` (assim como é feito no TableBuilder):
```csharp
public void Build(List<string> labels, List<float> values, string chartTitle = "")
{
    // ... ler e instanciar barras procedurais com base nos dados reais do JSON ...
}
```

---

## 5. Carregamento de Imagens e Figuras Germinadas

### Imagens Germinadas (Fatiamento Automático)
Figuras compostas contendo múltiplos sub-gráficos ou imagens lado a lado/verticais (geralmente figuras germinadas contendo sub-legendas a, b, c) são fatiadas automaticamente pelo backend Python no `image_extractor.py`.
* A nomenclatura padrão adotada para sub-imagens é: `FIG_N_X.png` (onde `N` é o número da figura no paper e `X` é a parte, ex: `FIG_3_1.png`, `FIG_3_2.png`).
* Elas são referenciadas sequencialmente no manifest sob a categoria `image` usando a ordem do `stackIndex`.

### Carregamento de Imagem no Unity:
O script de exibição de cartas de imagem do Unity deve carregar a imagem dinamicamente a partir do caminho listado no campo `relatedImage` (procurando no diretório local `Assets/PaperCaveData/{paper_id}/images/`).
* Recomenda-se usar `Resources.Load` (movendo os dados de cada paper para a pasta `Resources/` do Unity) ou carregar a textura diretamente do sistema de arquivos local (`System.IO.File.ReadAllBytes`) para aplicar à propriedade `texture` do `RawImage` da carta.
