"""
utils/unity_asset_exporter.py
Converts the complex ReviewedUnitManifest from the python pipeline output (07_reviewer_output.json)
into a flat JSON format (manifest.json) expected by Leo's Unity JsonSceneInstantiator.cs.
Also copies the generated figure assets to Assets/PaperCaveData/{paper_id}/images/.
"""
import json
import shutil
from pathlib import Path

def normalize_image_name(asset_ref: str) -> str:
    if not asset_ref:
        return ""
    ref = asset_ref.strip().upper()
    # Se já terminar com .png, remove para normalizar
    if ref.endswith(".PNG"):
        ref = ref[:-4]
    # Se começar com FIG_ ou FIG
    if ref.startswith("FIG_"):
        num = ref[4:]
    elif ref.startswith("FIG"):
        num = ref[3:]
    else:
        num = ref
    # Retorna no padrão FIG_N.png
    return f"FIG_{num}.png"


def export_assets_to_unity(paper_id: str, paper_folder: Path, unity_project_root: Path = Path("../")):
    """
    Exports the manifest.json and its figure assets directly to the Unity project structure.
    
    Target:
      - Manifest: {unity_project_root}/Assets/PaperCaveData/{paper_id}/manifest.json
      - Images:   {unity_project_root}/Assets/PaperCaveData/{paper_id}/images/FIG_*.png
    """
    # 1. Localizar o output do Reviewer
    output_dir = Path("outputs") / paper_id
    reviewer_output_path = output_dir / "07_reviewer_output.json"
    
    if not reviewer_output_path.exists():
        print(f"    [Exporter] Erro: arquivo de output {reviewer_output_path} não encontrado.")
        return False
        
    print(f"    [Exporter] Lendo output do reviewer de {reviewer_output_path}...")
    
    # 2. Carregar dados da pipeline
    with open(reviewer_output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # 3. Converter para o formato flat do Unity (SceneData / GameObjectData)
    unity_manifest = {
        "paperTitle": data.get("paperTitle", "Sem Título"),
        "centralContribution": data.get("centralContribution", ""),
        "gameObjects": []
    }
    
    units = data.get("units", [])
    for unit in units:
        unit_type = unit.get("type", "card")
        category = unit.get("category", "")
        conceptual_origin = unit.get("conceptualOrigin", "")
        why_this_five = unit.get("whyThisUnit", "")
        priority = unit.get("priority", "secondary")
        
        # Mapeamento do displayType
        def get_display_type(content_type):
            ct = (content_type or "").lower().strip()
            if ct == "figure":
                return "image"
            elif ct == "chart":
                return "graph"
            elif ct == "table":
                return "table"
            else:
                return "text"
                
        # Helper para dados de Tabela
        def format_table_data(content_data):
            headers_str = ""
            rows_str = ""
            cols_count = 0
            rows_count = 0
            if content_data and isinstance(content_data, dict):
                columns = content_data.get("columns", [])
                rows = content_data.get("rows", [])
                
                cols_count = len(columns)
                rows_count = len(rows)
                
                headers_str = "|".join(str(c).strip() for c in columns)
                
                row_lines = []
                for row in rows:
                    if isinstance(row, list):
                        row_lines.append("|".join(str(cell).strip() for cell in row))
                rows_str = ";".join(row_lines)
                
            return cols_count, rows_count, headers_str, rows_str

        # Helper para dados de Gráfico (proposta de extensão dinámica para o Leo)
        def format_graph_data(content_data):
            labels_str = ""
            values_str = ""
            if content_data and isinstance(content_data, dict):
                labels = content_data.get("labels", [])
                values = content_data.get("values", [])
                labels_str = "|".join(str(l).strip() for l in labels)
                values_str = "|".join(str(v).strip() for v in values)
            return labels_str, values_str

        # Caso seja uma carta simples (Card)
        if unit_type == "card":
            title = unit.get("title", "")
            content_type = unit.get("contentType", "text_panel")
            content = unit.get("content", {}) or {}
            
            description = content.get("description", "")
            asset_ref = content.get("assetReference", "")
            
            # Formatar dados de tabela ou gráfico se houver
            cols, rows, headers, row_data = format_table_data(content.get("data"))
            graph_labels, graph_values = format_graph_data(content.get("data"))
            
            # Se for figura, verificar o relatedImage usando a normalização
            related_img = normalize_image_name(asset_ref) if asset_ref else ""
            
            go_data = {
                "suggestedName": title or unit.get("id", "card"),
                "conceptualOrigin": conceptual_origin,
                "category": category,
                "visualMetaphor": description,
                "behaviourHint": f"Priority: {priority}",
                "interactionType": "Click to expand/drag",
                "whyThisFive": why_this_five,
                "relatedImage": related_img,
                "displayType": get_display_type(content_type),
                "rows": rows,
                "columns": cols,
                "tableHeaders": headers,
                "tableRows": row_data,
                # Extensões propostas
                "graphLabels": graph_labels,
                "graphValues": graph_values,
                "stackIndex": -1  # Indica que não faz parte de uma stack
            }
            unity_manifest["gameObjects"].append(go_data)
            
        # Caso seja uma stack
        elif unit_type == "stack":
            stack_label = unit.get("stackLabel", "Stack")
            items = unit.get("items", []) or []
            
            for item in items:
                idx = item.get("index", 0)
                item_title = item.get("title", "")
                content_type = item.get("contentType", "text_panel")
                content = item.get("content", {}) or {}
                
                description = content.get("description", "")
                asset_ref = content.get("assetReference", "")
                
                # Formatar dados de tabela ou gráfico se houver
                cols, rows, headers, row_data = format_table_data(content.get("data"))
                graph_labels, graph_values = format_graph_data(content.get("data"))
                
                related_img = normalize_image_name(asset_ref) if asset_ref else ""
                
                go_data = {
                    "suggestedName": item_title or f"{stack_label}_{idx}",
                    "conceptualOrigin": conceptual_origin,
                    "category": category,  # mesma categoria da stack pai (ex: image, graph, table)
                    "visualMetaphor": description,
                    "behaviourHint": f"Part of Stack: {stack_label}",
                    "interactionType": "Browse stack deck",
                    "whyThisFive": why_this_five,
                    "relatedImage": related_img,
                    "displayType": get_display_type(content_type),
                    "rows": rows,
                    "columns": cols,
                    "tableHeaders": headers,
                    "tableRows": row_data,
                    # Extensões propostas
                    "graphLabels": graph_labels,
                    "graphValues": graph_values,
                    "stackIndex": idx  # Identifica a ordem no deck de cartas
                }
                unity_manifest["gameObjects"].append(go_data)
                
    # 4. Criar diretórios no Unity e salvar
    unity_dest_dir = unity_project_root / "Assets" / "PaperCaveData" / paper_id
    unity_images_dir = unity_dest_dir / "images"
    
    unity_dest_dir.mkdir(parents=True, exist_ok=True)
    unity_images_dir.mkdir(parents=True, exist_ok=True)
    
    # Salvar o manifest flat do Unity
    unity_manifest_path = unity_dest_dir / "manifest.json"
    print(f"    [Exporter] Salvando manifest.json flat em {unity_manifest_path}...")
    with open(unity_manifest_path, "w", encoding="utf-8") as f:
        json.dump(unity_manifest, f, ensure_ascii=False, indent=2)
        
    # Limpar qualquer arquivo reviewer_manifest_original.json antigo para manter a pasta limpa
    original_manifest_path = unity_dest_dir / "reviewer_manifest_original.json"
    if original_manifest_path.exists():
        try:
            original_manifest_path.unlink()
        except Exception:
            pass
        
    # 5. Copiar todas as figuras da pasta do paper
    print(f"    [Exporter] Copiando imagens FIG_*.png de {paper_folder} para {unity_images_dir}...")
    copied_count = 0
    for img_file in paper_folder.glob("FIG*.png"):
        dest_file = unity_images_dir / img_file.name
        shutil.copy2(img_file, dest_file)
        copied_count += 1
        
    print(f"    [Exporter] Exportação concluída com sucesso!")
    print(f"      - Manifest salvo: {unity_manifest_path}")
    print(f"      - Imagens copiadas: {copied_count} arquivo(s) em {unity_images_dir}")
    return True

if __name__ == "__main__":
    # Teste de execução isolada do exporter
    import sys
    if len(sys.argv) < 3:
        print("Uso: python unity_asset_exporter.py <paper_id> <paper_folder_path> [unity_project_root_path]")
        sys.exit(1)
        
    pid = sys.argv[1]
    p_folder = Path(sys.argv[2])
    u_root = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("../../")
    export_assets_to_unity(pid, p_folder, u_root)
