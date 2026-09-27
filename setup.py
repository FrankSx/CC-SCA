from setuptools import setup, Extension

native = Extension(
    "sca_arsenal._native",
    sources=["sca_arsenal/_native.c"],
    extra_compile_args=["-O2"],
)

setup(ext_modules=[native])
