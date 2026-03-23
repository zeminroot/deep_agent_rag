使用 vLLM 部署paddleocr-vl模型启动服务接口

##### 1、创建虚拟环境
python -m venv .venv_vlm
##### 2、激活环境
source .venv_vlm/bin/activate
##### 3、安装 PaddleOCR
python -m pip install "paddleocr[doc-parser]"
##### 4、安装推理加速服务依赖
paddleocr install_genai_server_deps vllm

paddleocr install_genai_server_deps 命令用法：

paddleocr install_genai_server_deps <推理加速框架名称>

当前支持的框架名称为 vllm、sglang 和 fastdeploy，分别对应 vLLM、SGLang 和 FastDeploy。

通过 paddleocr install_genai_server_deps 安装的 vLLM 与 SGLang 均为 CUDA 12.6 版本，请确保本地 NVIDIA 驱动与此版本一致或更高。

##### 5、安装完成
通过 paddleocr genai_server 命令启动服务：

paddleocr genai_server --model_name PaddleOCR-VL-0.9B --backend vllm --port 8118

该命令支持的参数如下：

--model_name 模型名称
--model_dir 模型目录
--host 服务器主机名
--port 服务器端口号
--backend 后端名称，即使用的推理加速框架名称，可选 vllm 或 sglang
--backend_config 可指定 YAML 文件，包含后端配置


##### 6、详细步骤参考文章
https://mp.weixin.qq.com/s/Et52l5WSzvoBrJmNYl9U5g