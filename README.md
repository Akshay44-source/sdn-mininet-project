# 🚀 SDN Path Tracing Tool (Mininet + Ryu)

## 📌 Project Overview

This project implements a **Software Defined Networking (SDN) based Path Tracing Tool** using:

* **Ryu Controller (OpenFlow 1.3)**
* **Mininet Network Emulator**
* **NetworkX for graph-based path computation**

The system dynamically:

* Discovers network topology
* Learns host locations (MAC → switch, port)
* Computes **shortest paths**
* Installs flow rules across switches
* Provides **REST APIs + CLI visualization**

---

## 🧠 Core Idea

Instead of traditional routing, the controller:

* Maintains a **network graph**
* Computes shortest paths using algorithms
* Programs switches dynamically

---

## 🏗️ Network Topology

### 🔹 Linear Topology (default)

```
h1 ── s1 ── s2 ── s3 ── h3
            |
            h2
```

(Defined in )

---

## 📁 Project Structure

| File                  | Description                      |
| --------------------- | -------------------------------- |
| `path_tracer.py`      | Ryu controller (core logic)      |
| `mininet_topo.py`     | Network topology (linear + star) |
| `path_display.py`     | CLI dashboard & visualization    |
| `test_path_tracer.py` | Unit + REST API tests            |
| `requirements.txt`    | Dependencies                     |

---

## ⚙️ Features

### ✅ Controller Features ()

* Topology discovery using LLDP
* MAC learning (host tracking)
* Shortest path computation (NetworkX)
* Flow rule installation
* Path logging

### 🌐 REST API Endpoints

* `/topology` → network structure
* `/paths` → traced paths log
* `/path/<src>/<dst>` → specific path
* `/mac_table` → learned MAC table

---

## 🖥️ CLI Visualization ()

Run:

```bash
python3 path_display.py
```

Features:

* Live topology view
* Path visualization
* MAC table display
* Auto-refresh mode (`--watch`)
* Query specific paths

---

## 📦 Installation

### 1️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

(Dependencies defined in )

---

## ▶️ How to Run (Step-by-Step)

### 🟢 Step 1: Start Controller

```bash
ryu-manager path_tracer.py --observe-links
```

---

### 🟢 Step 2: Start Mininet

```bash
sudo python3 mininet_topo.py
```

---

### 🟢 Step 3: Generate Traffic

In Mininet CLI:

```bash
h1 ping h3
h1 ping h2
```

---

### 🟢 Step 4: View Paths

```bash
python3 path_display.py
```

---

## 🔍 Example Output

```
Route: h1 → h3

[h1] ══[S1]══ [S2] ══[S3]══ [h3]
Hops: 3
```

---

## 🧪 Testing

Run full test suite:

```bash
python3 test_path_tracer.py
```

Includes:

* Path correctness tests
* Graph validation
* REST API testing
  (see )

---

## 💡 Key Concepts Used

* Software Defined Networking (SDN)
* OpenFlow Protocol
* Graph Theory (Shortest Path)
* Network Emulation (Mininet)
* REST API Design

---

## 🚀 Future Improvements

* GUI visualization (web-based)
* Load balancing paths
* QoS-aware routing
* Multi-controller support

---

## 👨‍💻 Author

**Akshay Kumar**

---

## ⭐ Tip

Before running tests or APIs:
👉 Make sure you **run ping first**
(otherwise controller won’t know hosts)

---

## 📜 License

This project is for educational purposes.
