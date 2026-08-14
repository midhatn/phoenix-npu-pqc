import shutil
from pathlib import Path

def main():
    print("======================================================================")
    print("           PHOENIX SDR-DSP: REPOSITORY PACKAGING & DEPLOYMENT         ")
    print("======================================================================")

    root_dir = Path(r"C:\phoenix-sdr-dsp")
    deploy_dir = root_dir / "dist" / "phoenix_sdr_dsp"
    
    if deploy_dir.exists():
        shutil.rmtree(deploy_dir)
    deploy_dir.mkdir(parents=True, exist_ok=True)

    print(f"Deploy Directory: {deploy_dir}")

    # Copy Headers
    src_include = root_dir / "include"
    dst_include = deploy_dir / "include"
    if src_include.exists():
        shutil.copytree(src_include, dst_include)
        print("  [OK] Copied include/sdr_dsp headers")

    # Copy Tests & Benchmarks
    src_tests = root_dir / "tests"
    dst_tests = deploy_dir / "tests"
    if src_tests.exists():
        shutil.copytree(src_tests, dst_tests)
        print("  [OK] Copied test suites (M5, M6, M7, M8, M9, M10, M11, M12)")

    # Copy Runner and Documentation
    files_to_copy = [
        "run_all_silicon_tests.py",
        "README.md",
    ]
    for f in files_to_copy:
        src_f = root_dir / f
        if src_f.exists():
            shutil.copy(src_f, deploy_dir / f)
            print(f"  [OK] Copied {f}")

    print("\nPackage deployed successfully under:")
    print(f"  {deploy_dir}")
    print("\nAll deliverables are ready for integration, testing, or upstream release.")

if __name__ == "__main__":
    main()
