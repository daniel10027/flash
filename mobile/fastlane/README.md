# fastlane — Flash mobile (MOB-041 / MOB-042)

Signature iOS via **fastlane match** (certs/profils chiffrés dans un dépôt privé),
signature Android via keystore (variables `FLASH_KEYSTORE_*`).

| Lane | Effet |
|---|---|
| `fastlane android beta` | AAB prod → Firebase App Distribution (groupe `testeurs-internes`) |
| `fastlane android release` | AAB prod → Play Console piste `internal` |
| `fastlane ios beta` | IPA prod → TestFlight |
| `fastlane ios release` | IPA prod → App Store Connect (sans soumission auto) |

Variables attendues (fournies par les secrets CI) :
`FLASH_API_BASE_URL`, `FLASH_KEYSTORE_PATH/PASSWORD`, `FLASH_KEY_ALIAS/PASSWORD`,
`PLAY_SERVICE_ACCOUNT_JSON`, `MATCH_GIT_URL`, `MATCH_PASSWORD`,
`APP_STORE_CONNECT_API_KEY`, `FIREBASE_ANDROID_APP_ID`,
`FIREBASE_SERVICE_CREDENTIALS`.
