> ⚠️ **This project is deprecated: moe-aihelper**
>
> This repository contains an early prototype and is no longer maintained.
> The project has been **fully rewritten** and moved to a new repository:
>
> - 🔗 GitLab: [moeai-c @ GitLab](https://gitlab.dongzeyang.top/ydzat/moeai-c)
> - 🔗 GitHub Mirror: [moeai-c @ GitHub](https://github.com/ydzat/moeai-c)
>
> Please refer to the new repository for up-to-date code, documentation, and development progress.


# System Blueprint: Moe-AIHelper - A System-Level AI Assistant Integrated with Linux Kernel

## Overview

Moe-AIHelper is a system-level AI assistant designed to operate across user space and kernel space on a Linux-based platform. It provides AI-driven automation, context-aware behavior, and system-level orchestration by integrating advanced AI techniques with low-level system capabilities.

This blueprint outlines the architectural layers, responsibilities, communication mechanisms, and design considerations to guide the implementation of such a system.

---

## 0. Project Motivation

As I am currently taking two advanced courses — **Linux Kernel Programming (LKP)** and **Software Language Engineering (SLE)** — I have decided to transform Moe-AIHelper from an application-level project into a system-level AI assistant that integrates more deeply with the Linux operating system.

In the LKP course, the final goal is to build a Linux kernel or kernel module. Therefore, I aim to align Moe-AIHelper with the kernel I will develop, enabling deep integration and control at the system level.

At the same time, in the SLE course, I have been introduced to the use of modeling languages and the benefits of structural design through model-driven engineering. This inspired me to reconstruct Moe-AIHelper using a modeling-based approach for better modularity, clarity, and maintainability.

With this dual academic background, the project will be developed and maintained as a long-term evolving system. It serves both as a practical outcome of technical research and an exploration toward building intelligent operating system infrastructures.

---

## 1. Architecture Layers

### [1] User Space - AI Logic Layer

- **Component:** `moe-aihelperd` (User Space Daemon)
- **Language:** Python or C++
- **Responsibilities:**
  - Natural language processing (NLP)
  - Task planning and orchestration
  - User intent recognition
  - Interaction with AI models (e.g., LLMs)
  - Communication with system control layer
- **External Dependencies:**
  - PyTorch, Transformers, LangChain, etc.
  - D-Bus or gRPC for inter-process communication

### [2] User Space - System Control Bridge Layer

- **Component:** `sys-bridge` (Middleware between AI and Kernel)
- **Language:** C / C++
- **Responsibilities:**
  - Wrap system calls (e.g., process control, filesystem operations)
  - Expose high-level APIs to the AI logic
  - Facilitate secure and privileged operations
- **Mechanisms:**
  - Shared memory, UNIX domain sockets, ioctl, or Netlink sockets

### [3] Kernel Space - Extension Layer

- **Component:** `moe-kmod` (Moe Kernel Module)
- **Language:** C (Kernel-safe subset)
- **Responsibilities:**
  - Intercept system events via hooks (e.g., syscall table, Netfilter, LSM)
  - Expose controllable behaviors to user space
  - Enforce AI-driven decisions at the kernel level
  - Optional: monitor system behavior for feedback

### [4] Kernel Native Layer

- **Component:** Core Linux Kernel APIs and Services
- **Unmodified Linux kernel base**
- Provides the base platform, scheduling, memory management, etc.

---

## 2. Component Interactions

```
+-------------------------------+             +-----------------------+
|        AI Logic (Python)      |             |   System Control      |
|    moe-aihelperd (daemon)     |<===========>|   Bridge (C/C++)      |
+-------------------------------+     IPC     +-----------------------+
       |       |                                      |
       |       | Netlink / ioctl                      |
       V       V                                      V
+------------------------------------------------------------+
|           Kernel Module (moe-kmod)                         |
|    - Monitors syscalls, network, filesystems              |
|    - Enforces behavior (e.g., block, reroute, log)        |
|    - Sends system feedback to bridge                      |
+------------------------------------------------------------+
```

---

## 3. Key Use Cases

- **User-aware automation**: Automatically perform tasks (e.g., open apps, clean temp files) based on inferred user intent
- **AI-driven security**: Block suspicious processes based on LLM evaluation or behavior patterns
- **Context-aware scheduling**: Optimize resource usage depending on user activity or battery state
- **Intelligent prompt injection**: Feed kernel-level events (e.g., file access) into LLM for intelligent reactions

---

## 4. Design Principles

- **Modularity:** Components should be replaceable (e.g., swap AI engine or sys bridge)
- **Security-first:** Ensure kernel space access is restricted and properly sandboxed
- **Asynchronous IPC:** Use non-blocking communication between AI and bridge layers
- **Fallback compatibility:** If AI logic crashes, system remains stable via default kernel behavior

---

## 5. Development Roadmap

1. Prototype `moe-aihelperd` with LLM integration (Python)
2. Build `sys-bridge` wrapper for system calls with C++
3. Develop `moe-kmod` for kernel-level event interception
4. Integrate Netlink or ioctl communication between layers
5. Package as systemd service with auto-recovery and logging

---

## 6. Long-term Vision

- Full integration into intelligent OS (smart desktop assistant)
- Secure AI-managed syscall filtering and behavioral monitoring
- Language-adaptive interaction (supporting natural speech, shell commands, GUIs)

---

## 中文对照

### 概述

Moe-AIHelper 是一个设计于 Linux 基础上，基于用户态和内核端协同工作的系统级 AI 助手。它通过 AI 推理、上下文识别和系统级作置能力，实现智能化自动化操作。

### 关于本项目的缘起说明

由于我本学期正在同时学习 Linux Kernel Programming（LKP） 以及 Software Language Engineering（SLE），因此决定将原本应用层级的 Moe-AIHelper 改造为一个更接近系统核心的系统级 AI 助手程序。

LKP 课程最终会要求构建一个内核或内核模块，而我希望 Moe-AIHelper 能够与这个自定义内核实现配合工作，进行深层集成与控制。

另一方面，在 SLE 课程中，我开始学习建模语言及其结构化设计的优势，这激发了我将该系统以建模驱动方式进行规范建构的想法。

基于上述双重背景，本项目将作为一个长期演进的系统工程进行持续维护与拓展，既是技术研究成果的实践落地，也是对智能操作系统理念的探索实现。

### 结构层级

1. **AI 逻辑层（用户态）**：用于 LLM 分析和任务调度，通常用 Python 实现
2. **系统控制桥接层（用户态）**：作为 AI 逻辑和内核之间的中间层，用 C/C++ 实现
3. **内核扩展层**：进行 syscall hook、Netfilter 路由等内核级监控和操作，用 C 实现
4. **内核原生层**：Linux 内核基础服务（无需修改）

### 组件互动

- AI 逻辑层 通过 IPC 与桥接层交互，后者通过 Netlink/ioctl 与内核模块通信

### 关键场景

- 智能化安全控制
- 上下文识别应用
- 根据内核事件解析 LLM 反应

### 设计原则

- 模块化、安全优先、异步 IPC、系统耐振性

### 开发路线

1. Python 实现 AI daemon
2. C++ 实现 syscall 桥接层
3. C 实现内核扩展模块
4. 完善上下通信 + systemd 集成

### 远望

- AI 教育性操作系统
- 进化系统管理和行为检索
- 支持自然语言 + GUI + CLI 等多模态交互
