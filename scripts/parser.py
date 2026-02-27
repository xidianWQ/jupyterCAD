import json
import os
import glob
import shutil
from collections import defaultdict

def create_empty_jcad():
    return {"schemaVersion": "3.0.0", "objects": [], "options": {}, "metadata": {}, "outputs": {}}

class SemanticParser:
    def __init__(self, input_dir="operators", output_dir="models"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)


    def _get_operations_by_part(self):
        """将文件按零件名分组并按序号排序"""
        files = glob.glob(os.path.join(self.input_dir, "*.json"))
        part_dict = defaultdict(list)
        
        for f in files:
            basename = os.path.basename(f) # e.g. bearing_A1B2_001.json
            name_parts = basename.replace(".json", "").split("_")
            
            seq = int(name_parts[-1]) # 最后一个是序号 001
            part_name = "_".join(name_parts[:-1]) # 前面的是零件名 bearing_A1B2
            
            part_dict[part_name].append((seq, f))
            
        # 对每个零件内部的操作按序号进行排序
        for part in part_dict:
            part_dict[part].sort(key=lambda x: x[0])
            
        return part_dict

    def build_jcad(self, part_name, sorted_ops):
        """融合单零件的操作序列"""
        jcad_data = create_empty_jcad()
        objects = jcad_data["objects"]
        
        for seq, filepath in sorted_ops:
            with open(filepath, "r", encoding="utf-8") as f:
                op_data = json.load(f)
                
            action = op_data.get("action")
            feature = op_data.get("data")
            
            if action == "add":
                # 添加到对象列表末尾 (JupyterCAD是顺序执行的特征树)
                objects.append(feature)
                
            elif action == "modify":
                target_name = feature.get("name")
                for i, obj in enumerate(objects):
                    if obj["name"] == target_name:
                        # 更新参数
                        if "parameters" in feature:
                            obj["parameters"].update(feature["parameters"])
                        if "placement" in feature:
                            obj["placement"] = feature["placement"]
                        objects[i] = obj
                        break
                        
            elif action == "remove":
                target_name = feature.get("name")
                # 为简化，这里演示直接移除。真实情况可能需要像之前那样检测 cascade dependants
                objects = [obj for obj in objects if obj["name"] != target_name]

        jcad_data["objects"] = objects
        
        # 保存为 .jcad
        out_path = os.path.join(self.output_dir, f"{part_name}.jcad")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(jcad_data, f, indent=2)
        
        return len(objects)

    def run(self):
        part_dict = self._get_operations_by_part()
        print(f"找到 {len(part_dict)} 个独特的零件/装配体，开始融合...")
        
        for part_name, ops in part_dict.items():
            final_obj_count = self.build_jcad(part_name, ops)
            print(f"[{part_name}] 融合完成，包含了 {len(ops)} 步操作，最终特征树节点数: {final_obj_count}")

if __name__ == "__main__":
    parser = SemanticParser()
    parser.run()