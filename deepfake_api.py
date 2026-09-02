"""
Deepfake视频检测API服务
使用EfficientNetB0模型进行视频帧检测
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import cv2
import numpy as np
from PIL import Image
import tensorflow as tf
import os
import tempfile
import logging
from datetime import datetime
import time
import io
import base64

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 模型路径 - 使用绝对路径
import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(script_dir, 'DEEPFAKE_DETECTION_MODEL-main', 'streamlit', 'my_model.keras')

# 全局变量存储加载的模型
model = None

def load_model():
    """加载训练好的Deepfake检测模型"""
    global model
    global MODEL_PATH

    try:
        # 打印调试信息
        logger.info(f"当前工作目录: {os.getcwd()}")
        logger.info(f"脚本目录: {script_dir}")
        logger.info(f"尝试加载模型: {MODEL_PATH}")
        logger.info(f"模型文件存在: {os.path.exists(MODEL_PATH)}")

        if os.path.exists(MODEL_PATH):
            file_size = os.path.getsize(MODEL_PATH) / 1024 / 1024
            logger.info(f"模型文件大小: {file_size:.2f} MB")

            if file_size < 1:
                logger.error(f"❌ 模型文件太小或为空: {file_size:.2f} MB")
                return False

            # 尝试不同的加载方式
            try:
                model = tf.keras.models.load_model(MODEL_PATH)
                logger.info(f"✅ 模型加载成功: {MODEL_PATH}")
                return True
            except Exception as e1:
                logger.warning(f"标准加载失败: {e1}")
                logger.info("尝试使用 compile=False 加载...")
                try:
                    model = tf.keras.models.load_model(MODEL_PATH, compile=False)
                    logger.info(f"✅ 模型加载成功 (compile=False): {MODEL_PATH}")
                    return True
                except Exception as e2:
                    logger.error(f"所有加载方式都失败了")
                    logger.error(f"错误1: {e1}")
                    logger.error(f"错误2: {e2}")
                    raise e1
        else:
            logger.error(f"❌ 模型文件不存在: {MODEL_PATH}")
            # 尝试列出可能的位置
            logger.info("尝试搜索模型文件...")
            for root, dirs, files in os.walk(script_dir):
                if 'my_model.keras' in files:
                    found_path = os.path.join(root, 'my_model.keras')
                    logger.info(f"找到模型文件: {found_path}")
                    MODEL_PATH = found_path
                    return load_model()  # 递归调用
            return False
    except Exception as e:
        logger.error(f"❌ 模型加载失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def preprocess_frame(frame):
    """预处理视频帧"""
    try:
        # 转换为RGB
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # 调整大小为150x150
        img = cv2.resize(img, (150, 150))

        # 处理通道数
        if img.shape[-1] != 3:
            logger.warning(f"帧通道数异常: {img.shape[-1]}, 转换为3通道")
            img = np.stack([img] * 3, axis=-1)

        # 归一化
        img = img.reshape(1, 150, 150, 3)
        return img
    except Exception as e:
        logger.error(f"帧预处理失败: {str(e)}")
        return None

def analyze_video(video_path, batch_size=10):
    """
    分析视频文件，返回详细的检测结果

    Args:
        video_path: 视频文件路径
        batch_size: 批处理大小

    Returns:
        dict: 包含检测结果的字典
    """
    if model is None:
        return {
            'success': False,
            'error': '模型未加载'
        }

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {
                'success': False,
                'error': '无法打开视频文件'
            }

        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        logger.info(f"📹 视频信息: {total_frames}帧, {fps}fps, {duration:.2f}秒, {width}x{height}")

        frame_count = 0
        fake_count = 0
        real_count = 0
        frames = []
        frame_predictions = []  # 存储每帧的预测结果

        # 逐帧分析
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            timestamp = frame_count / fps if fps > 0 else frame_count

            # 预处理帧
            processed_frame = preprocess_frame(frame)
            if processed_frame is None:
                continue

            frames.append(processed_frame)

            # 批量预测
            if len(frames) >= batch_size:
                batch = np.vstack(frames)
                predictions = model.predict(batch, verbose=0)

                for i, p in enumerate(predictions):
                    pred_class = np.argmax(p)
                    confidence = float(np.max(p))

                    is_fake = (pred_class == 0)
                    if is_fake:
                        fake_count += 1
                    else:
                        real_count += 1

                    # 记录帧预测结果
                    frame_predictions.append({
                        'frame': frame_count - len(frames) + i + 1,
                        'timestamp': (frame_count - len(frames) + i + 1) / fps if fps > 0 else 0,
                        'prediction': 'fake' if is_fake else 'real',
                        'confidence': confidence
                    })

                frames = []

        # 处理剩余的帧
        if frames:
            batch = np.vstack(frames)
            predictions = model.predict(batch, verbose=0)

            for i, p in enumerate(predictions):
                pred_class = np.argmax(p)
                confidence = float(np.max(p))

                is_fake = (pred_class == 0)
                if is_fake:
                    fake_count += 1
                else:
                    real_count += 1

                frame_predictions.append({
                    'frame': frame_count - len(frames) + i + 1,
                    'timestamp': (frame_count - len(frames) + i + 1) / fps if fps > 0 else 0,
                    'prediction': 'fake' if is_fake else 'real',
                    'confidence': confidence
                })

        cap.release()

        # 计算统计信息
        fake_percentage = (fake_count / frame_count * 100) if frame_count > 0 else 0
        real_percentage = (real_count / frame_count * 100) if frame_count > 0 else 0

        # 判断最终结果
        is_deepfake = fake_percentage > 50

        # 生成时间轴分析
        timeline = generate_timeline(frame_predictions, duration)

        # 生成异常证据
        evidence = generate_evidence(frame_predictions, fps)

        result = {
            'success': True,
            'verdict': 'fake' if is_deepfake else 'real',
            'confidence': fake_percentage if is_deepfake else real_percentage,
            'statistics': {
                'total_frames': frame_count,
                'fake_frames': fake_count,
                'real_frames': real_count,
                'fake_percentage': round(fake_percentage, 2),
                'real_percentage': round(real_percentage, 2)
            },
            'video_info': {
                'duration': round(duration, 2),
                'fps': round(fps, 2),
                'resolution': f"{width}x{height}",
                'total_frames': total_frames
            },
            'timeline': timeline,
            'evidence': evidence,
            'frame_predictions': frame_predictions[:100]  # 只返回前100帧详情，避免数据过大
        }

        logger.info(f"✅ 分析完成: {frame_count}帧, 伪造率{fake_percentage:.2f}%")
        return result

    except Exception as e:
        logger.error(f"❌ 视频分析失败: {str(e)}")
        return {
            'success': False,
            'error': f'视频分析失败: {str(e)}'
        }

def generate_timeline(frame_predictions, duration):
    """根据帧预测生成时间轴"""
    if not frame_predictions:
        return []

    timeline = []
    segment_size = max(1, len(frame_predictions) // 10)  # 分成10段

    for i in range(0, len(frame_predictions), segment_size):
        segment_frames = frame_predictions[i:i+segment_size]
        fake_count = sum(1 for f in segment_frames if f['prediction'] == 'fake')
        fake_ratio = fake_count / len(segment_frames)

        start_time = segment_frames[0]['timestamp']
        end_time = segment_frames[-1]['timestamp']

        status = 'suspicious' if fake_ratio > 0.5 else 'normal'

        timeline.append({
            'start': round(start_time, 2),
            'end': round(end_time, 2),
            'status': status,
            'label': '⚠️' if status == 'suspicious' else '✓',
            'description': f"伪造帧占比: {fake_ratio*100:.1f}%"
        })

    return timeline

def generate_evidence(frame_predictions, fps):
    """生成异常证据列表"""
    evidence = []
    evidence_id = 1

    # 查找连续的伪造帧段
    consecutive_fake = 0
    fake_start_frame = None

    for i, pred in enumerate(frame_predictions):
        if pred['prediction'] == 'fake':
            if consecutive_fake == 0:
                fake_start_frame = pred['frame']
            consecutive_fake += 1
        else:
            if consecutive_fake >= 5:  # 连续5帧以上为伪造时记录
                evidence.append({
                    'id': evidence_id,
                    'severity': 'high' if consecutive_fake >= 20 else 'medium',
                    'description': f"检测到连续{consecutive_fake}帧为Deepfake伪造内容",
                    'timestamp': round((fake_start_frame / fps if fps > 0 else fake_start_frame), 2),
                    'confidence': 85 + min(15, consecutive_fake // 2)
                })
                evidence_id += 1
            consecutive_fake = 0

    # 检查最后一段
    if consecutive_fake >= 5:
        evidence.append({
            'id': evidence_id,
            'severity': 'high' if consecutive_fake >= 20 else 'medium',
            'description': f"检测到连续{consecutive_fake}帧为Deepfake伪造内容",
            'timestamp': round((fake_start_frame / fps if fps > 0 else fake_start_frame), 2),
            'confidence': 85 + min(15, consecutive_fake // 2)
        })

    return evidence

def generate_gradcam_heatmap(img_array, model, last_conv_layer_name=None):
    """
    生成Grad-CAM热图，用于可视化模型关注的区域
    """
    try:
        # 如果没有指定卷积层，自动查找最后一个卷积层
        if last_conv_layer_name is None:
            for layer in reversed(model.layers):
                if 'conv' in layer.name.lower():
                    last_conv_layer_name = layer.name
                    break

        if last_conv_layer_name is None:
            logger.warning("未找到卷积层，使用简单的分块检测方法")
            return None

        # 创建一个模型，输出最后卷积层的输出和最终预测
        grad_model = tf.keras.models.Model(
            [model.inputs],
            [model.get_layer(last_conv_layer_name).output, model.output]
        )

        # 计算梯度
        with tf.GradientTape() as tape:
            conv_outputs, predictions = grad_model(img_array)
            # 获取预测的类别（0是fake）
            pred_index = tf.argmax(predictions[0])
            class_channel = predictions[:, pred_index]

        # 计算类别输出相对于卷积输出的梯度
        grads = tape.gradient(class_channel, conv_outputs)

        # 全局平均池化梯度
        pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))

        # 将梯度权重应用到卷积输出
        conv_outputs = conv_outputs[0]
        pooled_grads = pooled_grads.numpy()
        conv_outputs = conv_outputs.numpy()

        for i in range(len(pooled_grads)):
            conv_outputs[:, :, i] *= pooled_grads[i]

        # 生成热图
        heatmap = np.mean(conv_outputs, axis=-1)

        # 归一化热图
        heatmap = np.maximum(heatmap, 0)
        if np.max(heatmap) != 0:
            heatmap /= np.max(heatmap)

        return heatmap

    except Exception as e:
        logger.error(f"Grad-CAM生成失败: {str(e)}")
        return None

def detect_tampered_regions_grid(img_array, model, grid_size=3):
    """
    使用网格分块方法检测篡改区域
    将图片分成多个区域，分别检测每个区域的可疑程度
    """
    original_size = img_array.shape[1:3]  # (150, 150)
    regions = []

    block_h = original_size[0] // grid_size
    block_w = original_size[1] // grid_size

    # 对每个网格块进行检测
    for i in range(grid_size):
        for j in range(grid_size):
            # 提取区域
            y1 = i * block_h
            y2 = min((i + 1) * block_h, original_size[0])
            x1 = j * block_w
            x2 = min((j + 1) * block_w, original_size[1])

            # 提取并调整区域大小
            region = img_array[0, y1:y2, x1:x2, :]
            region_resized = cv2.resize(region, (150, 150))
            region_resized = region_resized.reshape(1, 150, 150, 3)

            # 预测该区域
            pred = model.predict(region_resized, verbose=0)
            pred_class = np.argmax(pred)
            confidence = float(np.max(pred))

            # 如果是fake且置信度较高，记录该区域
            if pred_class == 0 and confidence > 0.6:
                regions.append({
                    'x1': x1,
                    'y1': y1,
                    'x2': x2,
                    'y2': y2,
                    'confidence': confidence
                })

    return regions

def detect_and_visualize_regions(original_img, img_array, model):
    """
    检测篡改区域并在原图上可视化
    返回标注后的图片和检测区域信息
    """
    # 尝试使用Grad-CAM
    heatmap = generate_gradcam_heatmap(img_array, model)

    regions = []

    if heatmap is not None:
        # 使用热图检测区域
        # 将热图调整到原图大小
        heatmap_resized = cv2.resize(heatmap, (original_img.shape[1], original_img.shape[0]))

        # 阈值化热图，找出高激活区域
        threshold = 0.5
        _, binary = cv2.threshold((heatmap_resized * 255).astype(np.uint8),
                                  int(threshold * 255), 255, cv2.THRESH_BINARY)

        # 找出轮廓
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 过滤小区域
        min_area = (original_img.shape[0] * original_img.shape[1]) * 0.02  # 至少占2%
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > min_area:
                x, y, w, h = cv2.boundingRect(contour)
                # 计算该区域的平均热图值作为置信度
                region_heat = heatmap_resized[y:y+h, x:x+w]
                confidence = float(np.mean(region_heat))

                regions.append({
                    'x1': int(x),
                    'y1': int(y),
                    'x2': int(x + w),
                    'y2': int(y + h),
                    'confidence': confidence
                })
    else:
        # 使用网格分块方法
        grid_regions = detect_tampered_regions_grid(img_array, model, grid_size=3)

        # 将坐标转换到原图尺寸
        scale_x = original_img.shape[1] / 150
        scale_y = original_img.shape[0] / 150

        for region in grid_regions:
            regions.append({
                'x1': int(region['x1'] * scale_x),
                'y1': int(region['y1'] * scale_y),
                'x2': int(region['x2'] * scale_x),
                'y2': int(region['y2'] * scale_y),
                'confidence': region['confidence']
            })

    # 在原图上画出检测框
    result_img = original_img.copy()
    for region in regions:
        # 画红色矩形框
        cv2.rectangle(result_img,
                     (region['x1'], region['y1']),
                     (region['x2'], region['y2']),
                     (0, 0, 255), 3)

        # 添加置信度标签
        label = f"{region['confidence']*100:.1f}%"
        cv2.putText(result_img, label,
                   (region['x1'], region['y1'] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    return result_img, regions

def analyze_image(image_file, progress_callback=None):
    """分析单张图片，检测篡改区域"""
    if model is None:
        return {
            'success': False,
            'error': '模型未加载'
        }

    try:
        # 记录开始时间
        start_time = time.time()

        if progress_callback:
            progress_callback(10, "正在加载图片...")

        # 读取原始图片（保留原始尺寸用于可视化）
        image_file.seek(0)  # 重置文件指针
        original_img = Image.open(image_file)
        original_img = np.array(original_img)

        # 处理RGBA
        if original_img.ndim == 3 and original_img.shape[-1] == 4:
            original_img = original_img[:, :, :3]
        elif original_img.ndim == 2:
            original_img = np.stack([original_img] * 3, axis=-1)

        # 转换为BGR（OpenCV格式）
        original_img_bgr = cv2.cvtColor(original_img, cv2.COLOR_RGB2BGR)

        if progress_callback:
            progress_callback(20, "正在预处理图片...")

        # 调整大小用于模型预测
        img_resized = cv2.resize(original_img, (150, 150))
        img_array = img_resized.reshape(1, 150, 150, 3)

        logger.info(f"📷 图片形状: 原始={original_img.shape}, 调整后={img_resized.shape}")

        if progress_callback:
            progress_callback(40, "正在进行整体检测...")

        # 整体预测
        prediction = model.predict(img_array, verbose=0)
        pred_class = np.argmax(prediction)
        confidence = float(np.max(prediction))

        is_fake = (pred_class == 0)

        if progress_callback:
            progress_callback(60, "正在检测篡改区域...")

        # 检测篡改区域（只在判定为fake时检测）
        regions = []
        result_img_base64 = None

        if is_fake:
            # 检测并可视化区域
            result_img, regions = detect_and_visualize_regions(original_img_bgr, img_array, model)

            if progress_callback:
                progress_callback(80, "正在生成结果图片...")

            # 将结果图片转换为base64
            _, buffer = cv2.imencode('.jpg', result_img)
            result_img_base64 = base64.b64encode(buffer).decode('utf-8')
        else:
            # 如果是真实图片，返回原图
            _, buffer = cv2.imencode('.jpg', original_img_bgr)
            result_img_base64 = base64.b64encode(buffer).decode('utf-8')

        # 计算处理时间
        processing_time = time.time() - start_time

        if progress_callback:
            progress_callback(100, "分析完成")

        result = {
            'success': True,
            'verdict': 'fake' if is_fake else 'real',
            'prediction': 'Fake' if is_fake else 'Real',
            'confidence': round(confidence * 100, 2),
            'tampered_regions': len(regions),
            'processing_time': round(processing_time, 2),
            'regions': regions,
            'result_image': result_img_base64,
            'raw_prediction': prediction.tolist()
        }

        logger.info(f"✅ 图片分析完成: {result['prediction']}, 置信度{result['confidence']}%, "
                   f"检测到{len(regions)}个篡改区域, 耗时{processing_time:.2f}秒")
        return result

    except Exception as e:
        logger.error(f"❌ 图片分析失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': f'图片分析失败: {str(e)}'
        }

@app.route('/api/deepfake/video', methods=['POST'])
def detect_video():
    """视频Deepfake检测API"""
    try:
        if 'video' not in request.files:
            return jsonify({
                'success': False,
                'error': '未提供视频文件'
            }), 400

        video_file = request.files['video']

        if video_file.filename == '':
            return jsonify({
                'success': False,
                'error': '文件名为空'
            }), 400

        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
            video_file.save(temp_file.name)
            temp_path = temp_file.name

        logger.info(f"📥 接收视频文件: {video_file.filename}")

        # 分析视频
        result = analyze_video(temp_path)

        # 删除临时文件
        try:
            os.unlink(temp_path)
        except:
            pass

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ API错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }), 500

@app.route('/api/deepfake/image', methods=['POST'])
def detect_image():
    """图片Deepfake检测API"""
    try:
        if 'image' not in request.files:
            return jsonify({
                'success': False,
                'error': '未提供图片文件'
            }), 400

        image_file = request.files['image']

        if image_file.filename == '':
            return jsonify({
                'success': False,
                'error': '文件名为空'
            }), 400

        logger.info(f"📥 接收图片文件: {image_file.filename}")

        # 分析图片
        result = analyze_image(image_file)

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ API错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }), 500

@app.route('/api/deepfake/image/stream', methods=['POST'])
def detect_image_stream():
    """图片Deepfake检测API（带进度流式响应）"""
    try:
        if 'image' not in request.files:
            return jsonify({
                'success': False,
                'error': '未提供图片文件'
            }), 400

        image_file = request.files['image']

        if image_file.filename == '':
            return jsonify({
                'success': False,
                'error': '文件名为空'
            }), 400

        logger.info(f"📥 接收图片文件（流式）: {image_file.filename}")

        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            image_file.save(temp_file.name)
            temp_path = temp_file.name

        def generate_progress():
            """生成进度更新的SSE流"""
            import json

            # 创建进度队列
            progress_queue = []

            def progress_callback(progress, message):
                progress_queue.append({'progress': progress, 'message': message, 'type': 'progress'})

            # 发送初始进度
            yield f"data: {json.dumps({'progress': 0, 'message': '开始分析...', 'type': 'progress'})}\n\n"

            # 重新打开文件进行分析
            with open(temp_path, 'rb') as f:
                from io import BytesIO
                file_obj = BytesIO(f.read())

                # 手动控制进度更新
                yield f"data: {json.dumps({'progress': 10, 'message': '正在加载图片...', 'type': 'progress'})}\n\n"

                # 分析图片
                result = analyze_image(file_obj, progress_callback=progress_callback)

                # 发送所有累积的进度更新
                for prog in progress_queue:
                    yield f"data: {json.dumps(prog)}\n\n"

            # 删除临时文件
            try:
                os.unlink(temp_path)
            except:
                pass

            # 发送最终结果
            yield f"data: {json.dumps({'progress': 100, 'message': '分析完成', 'type': 'complete', 'result': result})}\n\n"

        return app.response_class(
            generate_progress(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        logger.error(f"❌ API错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }), 500

@app.route('/api/deepfake/health', methods=['GET'])
def health_check():
    """健康检查API"""
    return jsonify({
        'status': 'running',
        'model_loaded': model is not None,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    logger.info("🚀 启动Deepfake检测API服务...")

    # 从环境变量读取端口，默认5003
    port = int(os.environ.get('PORT', 5003))

    # 加载模型
    if load_model():
        logger.info(f"✅ 服务就绪，监听端口: {port}")
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        logger.error("❌ 模型加载失败，无法启动服务")
