import os
import json
import struct
import pyvista as pv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def generate_model_thumbnail(input_path, output_image_path, resolution=(800, 600)):
    """
    读取 3D 模型文件 (obj, stl, glb) 并生成缩略图。
    
    :param input_path: 3D 模型文件路径
    :param output_image_path: 输出图片路径 (例如 .png 或 .jpg)
    :param resolution: 图片分辨率 (宽, 高)
    :return: 成功返回 True, 失败返回 False
    """
    try:
        # 1. 设置离屏绘图器 (Off-screen Plotter)
        # window_size 控制输出图片的分辨率
        pl = pv.Plotter(off_screen=True, window_size=resolution)
        
        # 2. 设置背景色 (通常白色或透明更适合缩略图)
        pl.set_background('white')
        
        # 3. 读取模型
        # PyVista 底层使用 VTK，支持大多数标准格式
        mesh = pv.read(input_path)
        
        # 4. 添加模型到场景
        # color: 设置默认材质颜色 (仅当模型本身无纹理时生效)
        # pbr: 启用基于物理的渲染 (让金属/光泽看起来更真实)
        if input_path.lower().endswith('.glb') or input_path.lower().endswith('.gltf'):
            # GLB 通常自带纹理，不需要强制设色
            pl.add_mesh(mesh)
        else:
            # STL/OBJ 经常是白模，给一个好看的默认色 (比如淡蓝色) 和平滑着色
            pl.add_mesh(mesh, color='lightgray', show_edges=False, smooth_shading=True)

        # 5. 增强视觉效果 (可选)
        # 开启 Eye Dome Lighting (EDL) 能显著增强 3D 深度感，特别是对复杂的 STL
        pl.enable_eye_dome_lighting()
        
        # 6. 设置相机位置
        pl.camera_position = (1, -1, -1)  # 'xy', 'xz', 'yz', 'iso' (等轴侧) 等
        pl.reset_camera()
        pl.camera.zoom(1.1) # 稍微放大一点，填满画面

        # 7. 保存截图
        pl.screenshot(output_image_path)
        
        # 8. 清理内存
        pl.close()
        
        return True

    except Exception as e:
        print(f"生成缩略图失败: {e}")
        return False
    
    
if __name__ == "__main__":
    for type in ['glb', 'stl', 'obj']:
        generate_model_thumbnail(f"components/test.{type}", f"/home/xidian/DTEditor/server/thumbnail/{type}.png")