from setuptools import setup, find_packages

setup(
    name="ai-perf-agent",
    version="1.0.0",
    description="AI Performance Agent for RHEL/Nginx optimization",
    author="PSAP Hackathon Team",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.39.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "ai-perf-agent=agent.main:main",
        ],
    },
    python_requires=">=3.10",
)
