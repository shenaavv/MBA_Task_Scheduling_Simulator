# MBA Task Scheduling Simulator — Kelompok 4


## Anggota Tim

| No | Nama                   | NRP        |
| -- | ---------------------- | ---------- |
| 1  | Kanafira Vanesha Putri | 5027241010 |
| 2  | Tiara Putri Prasetya   | 5027241013 |
| 3  | Dina Rahmadani         | 5027241065 |
| 4  | Zahra Khaalishah       | 5027241070 |
| 5  | S. Farhan Baig         | 5027241097 |

## Deskripsi

Proyek ini merupakan simulator penjadwalan cloud task menggunakan algoritma
**Modified Bat Algorithm (MBA)** dan CloudSim Plus. Simulator
membaca 100 task dari Google Cluster Workload Trace yang sudah ditransformasikan
ke schema CloudSim, lalu menjadwalkannya ke 8 VM pada 1 datacenter dengan 4
host heterogen.

Workload menggunakan model **Bag-of-Tasks (BoT)**, sehingga task independen
dan tidak memiliki dependency. Tujuan optimasi adalah:

- meminimalkan **makespan** (waktu penyelesaian seluruh task);
- meminimalkan **konsumsi energi** (model linear berbasis power idle/busy per VM).

---

## Kasus Dunia Nyata

Simulator ini memodelkan penjadwalan batch pekerjaan pada infrastruktur cloud
seperti **platform analitik e-commerce**. Pada jam sibuk, platform tersebut
perlu menjalankan pekerjaan ETL, agregasi transaksi, rekomendasi produk, dan
deteksi fraud secara bersamaan. Setiap pekerjaan memiliki panjang komputasi,
kebutuhan CPU (PE), dan kebutuhan memori yang berbeda, sedangkan VM memiliki
kapasitas dan kecepatan yang heterogen.

MBA digunakan untuk memilih VM bagi setiap pekerjaan agar waktu penyelesaian
seluruh batch dan energi datacenter rendah. FCFS tetap dijalankan sebagai
baseline sederhana: pekerjaan diproses berdasarkan urutan kedatangan dan
dibagikan round-robin. Model ini juga relevan untuk pipeline IoT, pemrosesan
log, dan rendering batch yang task-nya independen (Bag-of-Tasks).

---

## Algoritma MBA

**Modified Bat Algorithm** adalah metaheuristik berbasis populasi. Satu bat
direpresentasikan sebagai vektor integer, dengan posisi ke-i berisi indeks VM
untuk task ke-i.

### 1. Inisialisasi solusi
MBA membuat 16 kandidat assignment yang feasible. Task hanya diinisialisasikan
ke VM dengan jumlah PE yang cukup; jika tidak tersedia, digunakan VM terdekat
sebagai fallback agar simulasi tetap dapat berjalan.

### 2. Eksplorasi dan eksploitasi
Pada setiap iterasi, kandidat bergerak menuju solusi terbaik (best bat).
Frekuensi mengatur seberapa sering posisi mengikuti best bat, sedangkan
loudness yang menurun mengubah pencarian dari eksplorasi ke eksploitasi lokal.
Sebagian kecil posisi diacak ulang untuk menjaga keragaman populasi.

Skor kandidat memprioritaskan makespan dan memberi penalti kecil pada estimasi
energi:

### Pseudocode

```
Initialize 16 feasible bats and evaluate their scores
bestBat = bat with the lowest score
Repeat 80 iterations:
    Generate candidates using frequency, loudness, and random mutation
    Repair every changed task to a VM with sufficient PE
    Replace a bat when the candidate score improves
Return bestBat as the task-to-VM mapping
```

### Kompleksitas
- Waktu: **O(I × P × n)** — I iterasi, P jumlah bat, n task
- Ruang: **O(P × n + m)** — populasi assignment dan beban VM

---

## Arsitektur Cloud

### Host

| Host   | PE | RAM   | Storage  | Bandwidth |
| ------ | -- | ----- | -------- | --------- |
| Host 1 | 8  | 16 GB | 1000 GB  | 10 Gbps   |
| Host 2 | 8  | 16 GB | 1000 GB  | 10 Gbps   |
| Host 3 | 16 | 32 GB | 2000 GB  | 10 Gbps   |
| Host 4 | 16 | 32 GB | 2000 GB  | 10 Gbps   |

### Virtual Machine

| VM       | Host   | PE | RAM   | Storage | MIPS/PE |
| -------- | ------ | -- | ----- | ------- | ------- |
| VM1-VM2  | Host 1 | 2  | 4 GB  | 100 GB  | 1000    |
| VM3-VM4  | Host 2 | 4  | 8 GB  | 200 GB  | 1500    |
| VM5-VM6  | Host 3 | 4  | 8 GB  | 200 GB  | 2000    |
| VM7-VM8  | Host 4 | 8  | 16 GB | 500 GB  | 2500    |

`VmAllocationPolicyRoundRobin` memastikan dua VM ditempatkan pada setiap host.

### Model Energi

| VM      | Idle Power | Busy Power |
| ------- | ---------- | ---------- |
| VM1-VM2 | 50 W       | 150 W      |
| VM3-VM4 | 75 W       | 220 W      |
| VM5-VM6 | 100 W      | 300 W      |
| VM7-VM8 | 150 W      | 450 W      |

```
Energy = Σ (busyTime_i × powerBusy_i + idleTime_i × powerIdle_i)
```

---

## Dataset

Dataset utama berada di `cloudsim-plus-mba/dataset/tasks.csv`. File ini
adalah hasil transformasi 100 task dari **Google Cluster Workload Trace
Version 1** ke schema CloudSim Plus.

### Sumber dan Transformasi

Raw trace resmi Google tersimpan sebagai
`cloudsim-plus-mba/dataset/google-cluster-data-1.csv.gz`. Trace berisi
workload Borg selama 7 jam dengan kolom raw:

| Kolom Raw       | Keterangan                               |
| --------------- | ---------------------------------------- |
| `Time`          | Waktu pengamatan (detik)                 |
| `ParentID`      | ID job yang memiliki task                |
| `TaskID`        | ID task asli dari trace                  |
| `JobType`       | Tipe job (digunakan sebagai `priority`)  |
| `NrmlTaskCores` | Kebutuhan CPU yang dinormalisasi         |
| `NrmlTaskMem`   | Kebutuhan memori yang dinormalisasi      |

Script `prepare_google_trace.py` mengambil 100 `TaskID` unik pertama yang
memiliki kebutuhan CPU positif. Aturan transformasi:

```
lengthMI = max(1, round(NrmlTaskCores × 1_000_000))
pes      = max(1, min(4, ceil(NrmlTaskCores × 32)))
ramMB    = max(1024, round(NrmlTaskMem × 64 × 1024))
priority = JobType
```

### Schema CloudSim

| Kolom      | Keterangan                                              |
| ---------- | ------------------------------------------------------- |
| `taskId`   | ID task hasil pemilihan dari trace                      |
| `lengthMI` | Proxy panjang task (dari CPU normalized demand)         |
| `pes`      | Kebutuhan PE (dari CPU normalized demand)               |
| `ramMB`    | Kebutuhan RAM (dari memory normalized demand)           |
| `priority` | `JobType` dari trace                                    |

Untuk membuat ulang `tasks.csv` setelah raw trace tersedia:

```bash
python3 cloudsim-plus-mba/dataset/prepare_google_trace.py
```

---

## Struktur Proyek

```
MBA_Task_Scheduling_Simulator/
├── run.sh                              
├── run_scalability_experiment.py       # Script eksperimen skalabilitas & pembuat grafik
├── README.md                           
└── cloudsim-plus-mba/
    ├── pom.xml                         # Maven build file
    ├── dataset/
    │   ├── tasks.csv                   
    │   ├── prepare_google_trace.py     
    │   └── source_metadata.txt        
    ├── results/                       
    │   ├── run.log                    
    │   ├── mba_mapping.csv
    │   ├── metrics.txt                 
    │   ├── fcfs_metrics.txt          
    │   ├── scalability_results.csv     # Rekap data hasil 100-1000 tasks
    │   ├── graph_combined.png          # Grafik gabungan semua metrik
    │   ├── graph_makespan.png          # Grafik perbandingan makespan
    │   ├── graph_energy.png            # Grafik konsumsi energi
    │   ├── graph_throughput.png        # Grafik throughput
    │   ├── graph_avg_util.png          # Grafik rata-rata utilisasi VM
    │   └── graph_improvement.png       # Grafik persentase efisiensi MBA
    └── src/
        └── main/
            └── java/
                └── id/its/cloudtaskscheduling/
                    └── MBACloudTaskScheduling.java
```

---

## Output Simulasi

### `results/run.log`
Log lengkap mencakup:
- Dataset Load Log — setiap task yang dibaca dari CSV
- Host Creation Log — detail setiap host yang dibuat
- VM Creation Log — detail setiap VM beserta host target
- Cloudlet Creation Log — detail setiap cloudlet
- MBA Mapping Log — assignment task→VM beserta accumulated load
- VM Load Summary — distribusi beban per VM setelah scheduling
- Cloudlet Execution Results — waktu mulai, selesai, dan durasi
- Performance Metrics — makespan, energi, utilisasi, throughput
- FCFS Baseline — perbandingan dengan scheduling FCFS

### `results/mba_mapping.csv`
```
cloudletIndex,vmId,lengthMI,startTime,finishTime,execTime,status
0,6,31250,0.1000,12.6000,12.5000,SUCCESS
...
```

### `results/metrics.txt`
```
Tasks Completed : 100
Makespan        : xx.xxxx s
Total Energy    : xx.xxxx J
Avg VM Util.    : xx.xx %
Throughput      : x.xxxxxx tasks/s
```

---

## Persyaratan

- **JDK 17** atau lebih baru
- **Apache Maven** 3.6 atau lebih baru
- **Python 3.8+** dengan dependensi pada [`requirements.txt`](requirements.txt)
  (`matplotlib` dan `numpy`) untuk eksperimen skalabilitas dan pembuatan grafik
- **Bash** (untuk `run.sh`; di Windows gunakan Git Bash atau WSL)

---

## Cara Menjalankan

### 1. Simulasi Utama (CloudSim Plus)
Dari root repository:

```bash
./run.sh
```

Script secara otomatis:
1. Masuk ke folder `cloudsim-plus-mba`
2. Menjalankan `mvn compile exec:java` untuk simulasi MBA
3. Menjalankan FCFS baseline (`mvn exec:java -Dexec.args="fcfs"`)
4. Menyimpan semua output ke `cloudsim-plus-mba/results/run.log`

#### Menjalankan manual per algoritma:
```bash
# MBA
cd cloudsim-plus-mba
mvn compile exec:java

# FCFS Baseline
mvn exec:java -Dexec.args="fcfs"
```

### 2. Eksperimen Skalabilitas & Visualisasi Grafik (Python)
Untuk mengevaluasi performa MBA vs FCFS dari skala 100 hingga 1.000 tasks dan menghasilkan grafik visualisasi:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python run_scalability_experiment.py
```
Grafik dan file CSV akan tersimpan secara otomatis di direktori `cloudsim-plus-mba/results/`.

---

## Keunggulan MBA

MBA memberikan load balancing yang baik melalui pencarian populasi yang
terkendali. Dengan parameter 16 bat dan 80 iterasi, kompleksitasnya adalah
O(I × P × n), sehingga jumlah iterasi dan ukuran populasi dapat disesuaikan
dengan kebutuhan lingkungan cloud.

---

## Hasil Simulasi & Evaluasi

### 1. Hasil Single Run (100 Tasks Google Cluster Trace)

| Metrik | FCFS Baseline | MBA | Peningkatan |
| --- | --- | --- | --- |
| **Tasks Completed** | 100 | 100 | - |
| **Makespan** | 75.007.485.970,8740 s | **21.521.201.508,4937 s** | **~71,31% lebih cepat** |
| **Total Energy** | 86.493.133.946.367,3900 J | **47.745.859.148.706,4450 J** | **~44,80% lebih hemat** |
| **Avg VM Util.** | 39,91% | **97,32%** | **+57,41 poin persentase** |

---

### 2. Evaluasi Skalabilitas (100 - 1.000 Tasks)

Eksperimen menghasilkan baris untuk 100, 200, ..., 1.000 task dan menyimpan
metrik MBA serta FCFS pada `cloudsim-plus-mba/results/scalability_results.csv`.
Nilai pada grafik dihitung ulang dari algoritma MBA yang sama dengan simulasi
Java, sehingga tabel dan grafik tidak bergantung pada angka hard-coded.

---

### 3. Visualisasi Grafik Performa

#### Grafik Gabungan Semua Metrik
![Grafik Perbandingan Lengkap MBA vs FCFS](cloudsim-plus-mba/results/graph_combined.png)

<br/>

#### Perbandingan Makespan & Konsumsi Energi
| Makespan (Waktu Penyelesaian) | Konsumsi Energi (Joules) |
| :---: | :---: |
| ![Grafik Makespan](cloudsim-plus-mba/results/graph_makespan.png) | ![Grafik Konsumsi Energi](cloudsim-plus-mba/results/graph_energy.png) |

<br/>

#### Perbandingan Throughput & Rata-rata Utilisasi VM
| Throughput (Tasks/detik) | Rata-rata Utilisasi VM (%) |
| :---: | :---: |
| ![Grafik Throughput](cloudsim-plus-mba/results/graph_throughput.png) | ![Grafik Utilisasi VM](cloudsim-plus-mba/results/graph_avg_util.png) |

<br/>

#### Persentase Peningkatan Efisiensi MBA terhadap FCFS
![Grafik Persentase Peningkatan](cloudsim-plus-mba/results/graph_improvement.png)

---

## Lisensi Dataset

Google Cluster Workload Trace Version 1 dirilis di bawah lisensi
[Creative Commons Attribution (CC-BY)](https://creativecommons.org/licenses/by/4.0/).
Lihat `cloudsim-plus-mba/dataset/source_metadata.txt` untuk detail lengkap.
