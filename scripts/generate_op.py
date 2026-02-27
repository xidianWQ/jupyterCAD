import json
import os
import random
import uuid
import math
import shutil

class SemanticCADGenerator:
    def __init__(self, output_dir="operators"):
        self.output_dir = output_dir
        self.global_op_count = 0
        
        # 启动前清空历史脏数据
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

    def _save_op(self, part_name, seq_num, action, data):
        self.global_op_count += 1
        filepath = os.path.join(self.output_dir, f"{part_name}_{seq_num:03d}.json")
        op = {"action": action, "data": data}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(op, f, indent=2)

    def _base_placement(self, pos=(0,0,0)):
        """返回 Schema 要求的标准 Placement 结构"""
        return {"Position": list(pos), "Axis": [0, 0, 1], "Angle": 0}

    # ================= 零件模板 1：法兰 (Flange) =================
    def build_flange(self):
        uid = uuid.uuid4().hex[:4]
        part_name = f"flange_{uid}"
        seq = 1
        
        # 1. 基础圆柱体
        base_r = random.uniform(20, 50)
        base_h = random.uniform(5, 15)
        base_name = f"BaseCyl_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": base_name, "shape": "Part::Cylinder", "visible": True,
            "parameters": {
                "Radius": base_r, "Height": base_h, "Angle": 360, 
                "Placement": self._base_placement()
            }
        }); seq += 1

        # 【模拟用户行为：Modify】用户觉得基座太薄了，修改 Height
        if random.random() > 0.4:
            base_h += random.uniform(2, 5)
            self._save_op(part_name, seq, "modify", {
                "name": base_name,
                "parameters": {"Height": base_h}
            }); seq += 1

        # 2. 中心孔工具 (Cylinder)
        hole_r = random.uniform(5, base_r - 10)
        tool_name = f"CenterHoleTool_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": tool_name, "shape": "Part::Cylinder", "visible": False,
            "parameters": {
                "Radius": hole_r, "Height": base_h + 2, "Angle": 360, 
                "Placement": self._base_placement((0, 0, -1))
            }
        }); seq += 1

        # 3. 中心孔切除 (Cut)
        cut1_name = f"MainCut_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": cut1_name, "shape": "Part::Cut", "visible": True,
            "dependencies": [base_name, tool_name],
            "parameters": {
                "Base": base_name, "Tool": tool_name, 
                "Refine": False, "Placement": self._base_placement()
            }
        }); seq += 1

        # 【模拟用户行为：Remove】用户不小心建了一个多余的切除工具，然后把它删除了
        if random.random() > 0.6:
            mistake_name = f"MistakeTool_{uid}"
            self._save_op(part_name, seq, "add", {
                "name": mistake_name, "shape": "Part::Cylinder", "visible": True,
                "parameters": {"Radius": 5, "Height": 10, "Angle": 360, "Placement": self._base_placement()}
            }); seq += 1
            self._save_op(part_name, seq, "remove", {
                "name": mistake_name
            }); seq += 1

        # 4. 周围的螺栓孔 (模拟阵列)
        num_holes = random.choice([4, 6, 8])
        bolt_r = random.uniform(2, 4)
        pitch_r = base_r - bolt_r - 2
        
        current_base = cut1_name
        for i in range(num_holes):
            angle = 2 * math.pi * i / num_holes
            hx, hy = pitch_r * math.cos(angle), pitch_r * math.sin(angle)
            
            btool = f"BoltTool_{uid}_{i}"
            self._save_op(part_name, seq, "add", {
                "name": btool, "shape": "Part::Cylinder", "visible": False,
                "parameters": {
                    "Radius": bolt_r, "Height": base_h + 2, "Angle": 360,
                    "Placement": self._base_placement((hx, hy, -1))
                }
            }); seq += 1
            
            next_cut = f"BoltCut_{uid}_{i}"
            self._save_op(part_name, seq, "add", {
                "name": next_cut, "shape": "Part::Cut", "visible": True,
                "dependencies": [current_base, btool],
                "parameters": {
                    "Base": current_base, "Tool": btool, 
                    "Refine": False, "Placement": self._base_placement()
                }
            }); seq += 1
            current_base = next_cut

        # 【模拟用户行为：Modify】最终调整一下中心孔的尺寸
        if random.random() > 0.3:
            self._save_op(part_name, seq, "modify", {
                "name": tool_name,
                "parameters": {"Radius": hole_r + 1}
            }); seq += 1


    # ================= 零件模板 2：L型支架 (L-Bracket) =================
    def build_l_bracket(self):
        uid = uuid.uuid4().hex[:4]
        part_name = f"bracket_{uid}"
        seq = 1

        w, d, t = random.uniform(20,40), random.uniform(10,30), random.uniform(3,8)
        h = random.uniform(20, 50)

        # 1. 底部和侧边 Box
        box1 = f"BaseBox_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": box1, "shape": "Part::Box", "visible": True,
            "parameters": {
                "Length": w, "Width": d, "Height": t, 
                "Placement": self._base_placement()
            }
        }); seq += 1

        # 【模拟用户行为：Modify】建好第一块板后调整其长度
        if random.random() > 0.5:
            w += random.uniform(5, 10)
            self._save_op(part_name, seq, "modify", {
                "name": box1,
                "parameters": {"Length": w}
            }); seq += 1

        box2 = f"WallBox_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": box2, "shape": "Part::Box", "visible": True,
            "parameters": {
                "Length": t, "Width": d, "Height": h, 
                "Placement": self._base_placement()
            }
        }); seq += 1

        # 2. 融合 (MultiFuse)
        fuse_name = f"BracketFuse_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": fuse_name, "shape": "Part::MultiFuse", "visible": True,
            "dependencies": [box1, box2],
            "parameters": {
                "Shapes": [box1, box2],
                "Refine": False,     
                "Placement": self._base_placement()
            }
        }); seq += 1

        # 3. 倒角/圆角 (Fillet)
        if random.random() > 0.3:
            fillet_name = f"Fillet_{uid}"
            self._save_op(part_name, seq, "add", {
                "name": fillet_name, "shape": "Part::Fillet", "visible": True,
                "dependencies": [fuse_name],
                "parameters": {
                    "Base": fuse_name, "Radius": t/2, 
                    "Edge": [1, 2], # 【修复】Schema 规定字段为 Edge
                    "Placement": self._base_placement() # 【修复】补全 Placement
                }
            }); seq += 1

            # 【模拟用户行为：Remove】倒角做完后觉得不好看，又撤销/删除了倒角
            if random.random() > 0.6:
                self._save_op(part_name, seq, "remove", {
                    "name": fillet_name
                }); seq += 1


    # ================= 零件模板 3：阶梯轴 (Stepped Shaft) =================
    def build_stepped_shaft(self):
        uid = uuid.uuid4().hex[:4]
        part_name = f"shaft_{uid}"
        seq = 1

        sections = random.randint(2, 4)
        cyls = []
        z_offset = 0

        # 生成多段 Cylinder
        for i in range(sections):
            r = random.uniform(5, 20)
            h = random.uniform(10, 40)
            cname = f"Sec_{i}_{uid}"
            self._save_op(part_name, seq, "add", {
                "name": cname, "shape": "Part::Cylinder", "visible": True,
                "parameters": {
                    "Radius": r, "Height": h, "Angle": 360, 
                    "Placement": self._base_placement((0, 0, z_offset))
                }
            }); seq += 1
            cyls.append(cname)
            z_offset += h

        # 【模拟用户行为：Modify】修改中间某段圆柱的半径和位置 (Placement)
        if len(cyls) > 1 and random.random() > 0.4:
            target_cyl = cyls[1]
            self._save_op(part_name, seq, "modify", {
                "name": target_cyl,
                "parameters": {"Radius": random.uniform(25, 30)},
                "placement": self._base_placement((0, 0, 15)) # 模拟微调位置
            }); seq += 1

        # 将它们全部 Fuse 起来
        fuse_name = f"ShaftFuse_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": fuse_name, "shape": "Part::MultiFuse", "visible": True,
            "dependencies": cyls,
            "parameters": {
                "Shapes": cyls,
                "Refine": False,   
                "Placement": self._base_placement()
            }
        }); seq += 1

    # ================= 零件模板 4：带孔安装座 (Mounting Block) =================
    def build_mounting_block(self):
        uid = uuid.uuid4().hex[:4]
        part_name = f"mount_{uid}"
        seq = 1

        w = random.uniform(40, 60)
        h_base = random.uniform(5, 10)
        h_boss = random.uniform(10, 20)
        
        # 1. 基础底板 (Box) - 居中放置
        box_name = f"BaseBox_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": box_name, "shape": "Part::Box", "visible": True,
            "parameters": {
                "Length": w, "Width": w, "Height": h_base, 
                "Placement": self._base_placement((-w/2, -w/2, 0))
            }
        }); seq += 1

        # 2. 中心凸台 (Cylinder)
        boss_name = f"BossCyl_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": boss_name, "shape": "Part::Cylinder", "visible": True,
            "parameters": {
                "Radius": w/4, "Height": h_boss, "Angle": 360, 
                "Placement": self._base_placement((0, 0, h_base))
            }
        }); seq += 1

        # 【模拟用户行为：Modify】用户觉得凸台太高了，降低高度
        if random.random() > 0.4:
            self._save_op(part_name, seq, "modify", {
                "name": boss_name,
                "parameters": {"Height": h_boss - 2}
            }); seq += 1

        # 3. 融合底板和凸台
        fuse_name = f"MountFuse_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": fuse_name, "shape": "Part::MultiFuse", "visible": True,
            "dependencies": [box_name, boss_name],
            "parameters": {
                "Shapes": [box_name, boss_name],
                "Refine": False,
                "Placement": self._base_placement()
            }
        }); seq += 1

        # 4. 四个角的安装孔
        hole_r = random.uniform(2, 4)
        offset = w/2 - 6
        current_base = fuse_name
        
        positions = [
            (offset, offset, -1), (-offset, offset, -1), 
            (offset, -offset, -1), (-offset, -offset, -1)
        ]
        
        for i, pos in enumerate(positions):
            htool = f"HoleTool_{uid}_{i}"
            self._save_op(part_name, seq, "add", {
                "name": htool, "shape": "Part::Cylinder", "visible": False,
                "parameters": {
                    "Radius": hole_r, "Height": h_base + 2, "Angle": 360,
                    "Placement": self._base_placement(pos)
                }
            }); seq += 1
            
            next_cut = f"HoleCut_{uid}_{i}"
            self._save_op(part_name, seq, "add", {
                "name": next_cut, "shape": "Part::Cut", "visible": True,
                "dependencies": [current_base, htool],
                "parameters": {
                    "Base": current_base, "Tool": htool, 
                    "Refine": False, "Placement": self._base_placement()
                }
            }); seq += 1
            current_base = next_cut

        # 【模拟用户行为：Remove】尝试给凸台加个圆角，但由于选错了边导致报错或不满意，直接删除
        if random.random() > 0.5:
            bad_fillet = f"BadFillet_{uid}"
            self._save_op(part_name, seq, "add", {
                "name": bad_fillet, "shape": "Part::Fillet", "visible": True,
                "dependencies": [current_base],
                "parameters": {
                    "Base": current_base, "Radius": 2, "Edge": [5], "Placement": self._base_placement()
                }
            }); seq += 1
            self._save_op(part_name, seq, "remove", {
                "name": bad_fillet
            }); seq += 1


    # ================= 零件模板 5：带槽皮带轮 (Grooved Wheel) =================
    def build_wheel(self):
        uid = uuid.uuid4().hex[:4]
        part_name = f"wheel_{uid}"
        seq = 1

        R = random.uniform(30, 60)
        H = random.uniform(10, 20)

        # 1. 轮子基座
        base_name = f"WheelBase_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": base_name, "shape": "Part::Cylinder", "visible": True,
            "parameters": {
                "Radius": R, "Height": H, "Angle": 360, 
                "Placement": self._base_placement()
            }
        }); seq += 1

        # 2. V型槽/圆槽削减工具 (使用 Torus 圆环体)
        groove_r = H / 2.5
        torus_name = f"GrooveTorus_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": torus_name, "shape": "Part::Torus", "visible": False,
            "parameters": {
                "Radius1": R, "Radius2": groove_r, # Radius1 为主半径，Radius2为管截面半径
                "Angle1": -180, "Angle2": 180, "Angle3": 360,
                "Placement": self._base_placement((0, 0, H/2))
            }
        }); seq += 1

        # 【模拟用户行为：Modify】用户在试图将皮带槽调深一点
        if random.random() > 0.4:
            groove_r += 1.5
            self._save_op(part_name, seq, "modify", {
                "name": torus_name,
                "parameters": {"Radius2": groove_r}
            }); seq += 1

        # 3. 切除皮带槽
        groove_cut = f"GrooveCut_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": groove_cut, "shape": "Part::Cut", "visible": True,
            "dependencies": [base_name, torus_name],
            "parameters": {
                "Base": base_name, "Tool": torus_name, 
                "Refine": False, "Placement": self._base_placement()
            }
        }); seq += 1

        # 4. 中心轴孔
        axle_r = random.uniform(5, 10)
        axle_tool = f"AxleTool_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": axle_tool, "shape": "Part::Cylinder", "visible": False,
            "parameters": {
                "Radius": axle_r, "Height": H + 2, "Angle": 360, 
                "Placement": self._base_placement((0, 0, -1))
            }
        }); seq += 1
        
        final_cut = f"AxleCut_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": final_cut, "shape": "Part::Cut", "visible": True,
            "dependencies": [groove_cut, axle_tool],
            "parameters": {
                "Base": groove_cut, "Tool": axle_tool, 
                "Refine": False, "Placement": self._base_placement()
            }
        }); seq += 1


    # ================= 零件模板 6：三通管接头 (T-Pipe Joint) =================
    def build_t_joint(self):
        uid = uuid.uuid4().hex[:4]
        part_name = f"tjoint_{uid}"
        seq = 1

        pipe_r = random.uniform(10, 20)
        thickness = random.uniform(2, 4)
        inner_r = pipe_r - thickness

        # 1. 外部主管道 (Z向)
        main_out = f"MainOut_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": main_out, "shape": "Part::Cylinder", "visible": True,
            "parameters": {
                "Radius": pipe_r, "Height": 80, "Angle": 360, 
                "Placement": self._base_placement((0, 0, -40))
            }
        }); seq += 1

        # 2. 外部支管道 (Y向) - 模拟用户利用 Axis 旋转
        branch_out = f"BranchOut_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": branch_out, "shape": "Part::Cylinder", "visible": True,
            "parameters": {
                "Radius": pipe_r, "Height": 40, "Angle": 360, 
                "Placement": {"Position": [0, 0, 0], "Axis": [1, 0, 0], "Angle": 90} # 绕X轴转90度躺平
            }
        }); seq += 1

        # 3. 融合外壳
        shell_fuse = f"ShellFuse_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": shell_fuse, "shape": "Part::MultiFuse", "visible": True,
            "dependencies": [main_out, branch_out],
            "parameters": {
                "Shapes": [main_out, branch_out], "Refine": False, "Placement": self._base_placement()
            }
        }); seq += 1

        # 4. 内部抽壳工具 (主管道内径 + 支管道内径)
        main_in = f"MainIn_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": main_in, "shape": "Part::Cylinder", "visible": False,
            "parameters": {
                "Radius": inner_r, "Height": 82, "Angle": 360, "Placement": self._base_placement((0, 0, -41))
            }
        }); seq += 1
        
        branch_in = f"BranchIn_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": branch_in, "shape": "Part::Cylinder", "visible": False,
            "parameters": {
                "Radius": inner_r, "Height": 42, "Angle": 360, 
                "Placement": {"Position": [0, 0, 0], "Axis": [1, 0, 0], "Angle": 90}
            }
        }); seq += 1

        # 【模拟用户行为：Modify】修改支管内部工具的长度，确保能完全打穿外壳
        if random.random() > 0.3:
            self._save_op(part_name, seq, "modify", {
                "name": branch_in,
                "parameters": {"Height": 45}
            }); seq += 1

        inner_fuse = f"InnerFuse_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": inner_fuse, "shape": "Part::MultiFuse", "visible": False,
            "dependencies": [main_in, branch_in],
            "parameters": {
                "Shapes": [main_in, branch_in], "Refine": False, "Placement": self._base_placement()
            }
        }); seq += 1

        # 5. 抽壳 (Cut 外壳 - 内壳)
        final_cut = f"HollowCut_{uid}"
        self._save_op(part_name, seq, "add", {
            "name": final_cut, "shape": "Part::Cut", "visible": True,
            "dependencies": [shell_fuse, inner_fuse],
            "parameters": {
                "Base": shell_fuse, "Tool": inner_fuse, 
                "Refine": False, "Placement": self._base_placement()
            }
        }); seq += 1
        
    # ================= 主控制流 =================
    def generate(self, target_count=40):
        templates = [self.build_flange, self.build_l_bracket, self.build_stepped_shaft,
                     self.build_mounting_block, self.build_wheel, self.build_t_joint]
        
        print("开始生成符合 JupyterCAD Schema 的语义特征操作序列...")
        while self.global_op_count < target_count:
            func = random.choice(templates)
            func()
            
        print(f"生成完毕！共生成 {self.global_op_count} 个操作文件，储存在 '{self.output_dir}' 目录。")

if __name__ == "__main__":
    gen = SemanticCADGenerator()
    # 为方便测试，这里默认设为生成100步左右，您可以改大
    gen.generate(2000)