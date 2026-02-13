import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os

plt.rcParams['font.family'] = 'NanumGothic'
sns.set_theme(style="whitegrid")

BASE_DIR = "../results/step13_tinyllama_idle"
OUTPUT_DIR = BASE_DIR

def plot_timeseries(run_dir, run_num):
    try:
        cpu = pd.read_csv(f"{run_dir}/system_cpu.csv", index_col=0)
        ram = pd.read_csv(f"{run_dir}/system_ram.csv", index_col=0)
        disk = pd.read_csv(f"{run_dir}/disk_util_mmcblk0.csv", index_col=0) # 또는 disk_io_mmcblk0.csv
        net = pd.read_csv(f"{run_dir}/net_eth0.csv", index_col=0)

        fig, axs = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle(f"Step 13 Run {run_num}: Idle Resource Usage (300s)", fontsize=16)

        # 1. CPU Usage
        axs[0, 0].plot(cpu.index, cpu.iloc[:, 0], color='tab:blue')
        axs[0, 0].set_title("CPU Usage")
        axs[0, 0].set_ylabel("Usage (%)")
        axs[0, 0].set_xlabel("Time (s)")

        # 2. RAM Usage
        axs[0, 1].plot(ram.index, ram.iloc[:, 0], color='tab:orange')
        axs[0, 1].set_title("RAM Usage")
        axs[0, 1].set_ylabel("Usage (MB)")
        axs[0, 1].set_xlabel("Time (s)")

        # 3. Disk Utilization
        axs[1, 0].plot(disk.index, disk.iloc[:, 0], color='tab:green')
        axs[1, 0].set_title("Disk Utilization (mmcblk0)")
        axs[1, 0].set_ylabel("Util (%)")
        axs[1, 0].set_xlabel("Time (s)")

        # 4. Network Traffic (eth0)
        if net.shape[1] >= 1:
            axs[1, 1].plot(net.index, net.iloc[:, 0], label='Received', color='tab:purple')
            if net.shape[1] > 1:
                axs[1, 1].plot(net.index, net.iloc[:, 1], label='Sent', color='tab:red')
            axs[1, 1].legend()
        axs[1, 1].set_title("Network Traffic (eth0)")
        axs[1, 1].set_ylabel("Bandwidth (KB/s)")
        axs[1, 1].set_xlabel("Time (s)")

        plt.tight_layout()
        plt.savefig(f"{run_dir}/fig1_timeseries.png")
        plt.close()
        print(f"Saved Fig1 for Run {run_num}")

        return (cpu.iloc[:, 0].mean(), ram.iloc[:, 0].mean(), 
                disk.iloc[:, 0].mean(), net.iloc[:, 0].mean())

    except Exception as e:
        print(f"Error plotting run {run_num}: {e}")
        return None

def plot_distribution(stats_list):
    if not stats_list:
        return

    df = pd.DataFrame(stats_list, columns=['Run', 'Mean_CPU', 'Mean_RAM', 'Mean_Disk', 'Mean_Net'])

    fig, axs = plt.subplots(1, 4, figsize=(20, 6))

    sns.boxplot(y=df['Mean_CPU'], ax=axs[0], color='lightblue')
    axs[0].set_title("Mean CPU (%)")

    sns.boxplot(y=df['Mean_RAM'], ax=axs[1], color='lightgreen')
    axs[1].set_title("Mean RAM (MB)")
    
    sns.boxplot(y=df['Mean_Disk'], ax=axs[2], color='salmon')
    axs[2].set_title("Mean Disk Util (%)")

    sns.boxplot(y=df['Mean_Net'], ax=axs[3], color='plum')
    axs[3].set_title("Mean Network (KB/s)")

    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/fig2_distribution.png")
    plt.close()
    print("Saved Fig2 Distribution plot")

def main():
    stats = []
    for i in range(1, 11):
        run_path = f"{BASE_DIR}/run_{i}"
        if os.path.exists(run_path):
            result = plot_timeseries(run_path, i)
            if result is not None:
                stats.append([i, *result])

    plot_distribution(stats)

if __name__ == "__main__":
    main()
