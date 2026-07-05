# SOP —— Windows 代码签名

> 目标：消除 Orbit.exe 的 SmartScreen "Windows 已保护你的电脑" 警告。
> 状态：待商用阶段执行。当前双击 "仍要运行" 即可。

## 1. 为什么需要

Windows SmartScreen 对未签名的 `.exe` 弹出红色警告，降低用户信任。
数字签名后，发布者名称显示在 UAC 弹窗中，SmartScreen 信誉随时间积累消失。

## 2. 证书类型

| 类型 | 价格 | 要求 | SmartScreen 信誉 |
|------|------|------|:--:|
| 自签名 | 免费 | 无 | 仅本机信任 |
| OV (Organization Validation) | $80-200/年 | 营业执照 | 缓慢积累 |
| EV (Extended Validation) | $300-500/年 | 营业执照 + USB 硬件令牌 | 即时信誉 |

**建议**：商用后购买 OV 证书（DigiCert 或 Sectigo）。

## 3. 签名步骤

### 3.1 获取证书

1. 向 CA（如 DigiCert）提交企业资料
2. 验证通过后下载 `.pfx` 文件

### 3.2 签名命令

```bash
# 设置证书路径
export CODE_SIGN_CERT="D:/certs/orbit.pfx"
export CODE_SIGN_PASSWORD="<password>"

# 签名
signtool sign /fd SHA256 /f "$CODE_SIGN_CERT" /p "$CODE_SIGN_PASSWORD" \
  /tr http://timestamp.digicert.com /td SHA256 \
  "Deliverables/Orbit.exe"

# 验证
signtool verify /pa "Deliverables/Orbit.exe"
```

### 3.3 集成到 build-desktop.sh

在 `build-desktop.sh` 末尾添加（已有占位）：

```bash
if [ -n "$CODE_SIGN_CERT" ] && [ -n "$CODE_SIGN_PASSWORD" ]; then
  signtool sign /fd SHA256 /f "$CODE_SIGN_CERT" /p "$CODE_SIGN_PASSWORD" \
    /tr http://timestamp.digicert.com /td SHA256 \
    "Deliverables/Orbit.exe"
  echo "✅ 代码签名完成"
else
  echo "⚠️  跳过代码签名（CODE_SIGN_CERT 未设置）"
fi
```

## 4. 验证

1. 右键 `Orbit.exe` → 属性 → 数字签名（应有条目）
2. 新机器首次下载运行——SmartScreen 警告不应出现
3. 签名过期前 30 天续签
