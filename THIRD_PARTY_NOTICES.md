# 第三方软件声明

本分享包的 `third_party/tools/` 里附带了三个第三方开源软件的**官方发布文件，未做任何修改**，仅供接入对应平台时使用。
它们各自的版权和许可条款归原作者所有，使用前请阅读各自项目的说明。

| 软件 | 版本 | 用途 | 来源 | 许可 |
|---|---|---|---|---|
| WeChatDataAnalysis | 2.10.0 | 读取本机微信的聊天记录 | <https://github.com/LifeArchiveProject/WeChatDataAnalysis> | 仓库未提供许可证文件。其 README 声明：仅可用于处理使用者本人合法持有、管理或已取得明确授权访问的数据；桌面安装包为官方发布的构建 |
| NapCatQQ | 4.18.41 | 通过 OneBot 11 读取 QQ 群消息 | <https://github.com/NapNeko/NapCatQQ> | Limited Redistribution License（全文见下，**禁止商业使用**） |
| lark-cli | 1.0.98 | 飞书官方命令行工具 | <https://github.com/larksuite/cli> | MIT（全文见下） |

文件完整性：`WeChatDataAnalysis` 的安装程序附带官方 SHA-256 清单；`NapCat.Shell.zip` 的 SHA-256 为
`6801f93e533846cea05f4f531874a0e84371ab2331c5585b57cd7e3b869cf96b`。「安装接入工具.bat」会在使用前自动校验。

**请注意：**
- 这些软件与微信、腾讯（QQ）、飞书无隶属或授权关系，均为第三方工具。
- 请只读取你自己账号里的聊天内容，并遵守各平台的服务条款和相关法律法规。
- 想要最新版本，可以到上表的项目主页下载，或运行 `scripts/tools/get-*.ps1`。

---

## NapCatQQ — Limited Redistribution License

来源：<https://github.com/NapNeko/NapCatQQ/blob/main/LICENSE>

```
Limited Redistribution License for NapCat

Copyright © 2024 Mlikiowa

1. Usage and Reproduction:
   - Unauthorized use, reproduction, modification, or distribution of this code is prohibited without explicit permission from the main author of the NapCat repository.
   
2. Redistribution:
   - Redistribution of this code is permitted, provided that the full text of this license is included, and the source and copyright information is clearly stated.
   - Minor modifications and extensions are allowed for redistribution purposes, but the modified code must not be publicly released.

3. Non-Commercial Use:
   - This code is not to be used for any commercial purposes.

4. Additional Permissions:
   - Any rights not explicitly addressed in this license must be requested from and granted by the main author of the NapCat repository.

5. Disclaimer:
   - This code is provided "as is," without any express or implied warranties, including but not limited to the implied warranties of merchantability and fitness for a particular purpose. In no event shall the author be liable for any damages or other liability arising from, out of, or in connection with the use or distribution of this code.
```

---

## lark-cli — MIT License

来源：<https://github.com/larksuite/cli/blob/main/LICENSE>

```
MIT License

Copyright (c) 2026 Lark Technologies Pte. Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
