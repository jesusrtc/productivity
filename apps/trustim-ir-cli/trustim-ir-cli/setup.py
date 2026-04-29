import setuptools

from distgradle import GradleDistribution


setuptools.setup(
    distclass=GradleDistribution,
    package_dir={'': 'src'},
    packages=setuptools.find_packages('src'),
    include_package_data=True,
    python_requires='>=3.9',
    install_requires=[
        'click>=8.0',
        'requests>=2.28',
        'beautifulsoup4>=4.12',
        'tabulate>=0.9',
        'toml>=0.10',
    ],
    entry_points={
        'console_scripts': [
            'ir = trustimircli.cli:cli',
        ],
    },
)
