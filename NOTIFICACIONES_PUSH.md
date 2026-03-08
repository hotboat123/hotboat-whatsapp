# 📱 Sistema de Notificaciones Push - HotBoat WhatsApp

## 🎯 Objetivo

Reemplazar las notificaciones por email (que cuestan dinero) con **notificaciones push gratuitas** a tu teléfono móvil usando Expo.

## ✅ Ventajas

- ✅ **100% GRATIS** (sin límites con Expo Push Notifications)
- ✅ Notificaciones instantáneas a tu celular
- ✅ Funciona en iOS y Android
- ✅ No más costos de email
- ✅ Más rápido que email
- ✅ Notificaciones con sonido y vibración

---

## 🚀 Paso 1: Migración de Base de Datos

Ejecuta en tu servidor Railway:

```bash
railway run python run_migration_010.py
```

Esto crea la tabla `push_tokens` para almacenar los tokens de tu dispositivo.

---

## 📱 Paso 2: Crear la App Móvil (Opción Fácil)

### Opción A: Expo Go (MÁS RÁPIDO - 5 minutos)

1. **Instala Expo Go en tu celular:**
   - iOS: https://apps.apple.com/app/expo-go/id982107779
   - Android: https://play.google.com/store/apps/details?id=host.exp.exponent

2. **Crea una cuenta gratis en Expo:**
   - Ve a: https://expo.dev/signup
   - Crea tu cuenta (es gratis)

3. **Crea tu app con Expo Snack (ONLINE - sin código en tu PC):**
   - Ve a: https://snack.expo.dev/
   - Copia y pega el código del archivo `MOBILE_APP_CODE.js` (abajo)
   - Escanea el QR con Expo Go
   - ¡Listo! Ya tienes la app funcionando

### Opción B: App Nativa (más trabajo pero más profesional)

Si quieres una app standalone (publicada en App Store/Play Store), sigue las instrucciones en `MOBILE_APP_NATIVE.md`.

---

## 📄 Código de la App Móvil (Expo Snack)

Copia este código en https://snack.expo.dev/

```javascript
// MOBILE_APP_CODE.js
import React, { useState, useEffect, useRef } from 'react';
import { StyleSheet, Text, View, Button, Platform, Alert } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';

// CAMBIA ESTA URL POR LA DE TU SERVIDOR RAILWAY
const API_URL = 'https://hotboat-whatsapp-production.up.railway.app';

// Configurar cómo se muestran las notificaciones
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export default function App() {
  const [expoPushToken, setExpoPushToken] = useState('');
  const [notification, setNotification] = useState(false);
  const notificationListener = useRef();
  const responseListener = useRef();

  useEffect(() => {
    registerForPushNotificationsAsync().then(token => {
      setExpoPushToken(token);
      // Registrar el token en tu servidor
      if (token) {
        registerTokenWithServer(token);
      }
    });

    // Listener para notificaciones recibidas mientras la app está abierta
    notificationListener.current = Notifications.addNotificationReceivedListener(notification => {
      setNotification(notification);
    });

    // Listener para cuando el usuario toca la notificación
    responseListener.current = Notifications.addNotificationResponseReceivedListener(response => {
      console.log('Notification tapped:', response);
      const data = response.notification.request.content.data;
      Alert.alert(
        'Mensaje de WhatsApp',
        `De: ${data.contact_name}\nTeléfono: ${data.phone_number}`
      );
    });

    return () => {
      Notifications.removeNotificationSubscription(notificationListener.current);
      Notifications.removeNotificationSubscription(responseListener.current);
    };
  }, []);

  const registerTokenWithServer = async (token) => {
    try {
      const response = await fetch(`${API_URL}/api/push/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token: token,
          device_info: {
            platform: Platform.OS,
            device: Device.modelName,
            brand: Device.brand,
          },
        }),
      });

      if (response.ok) {
        console.log('✅ Token registrado en el servidor');
        Alert.alert('Éxito', 'Notificaciones activadas correctamente');
      } else {
        console.error('Error registrando token');
        Alert.alert('Error', 'No se pudo activar las notificaciones');
      }
    } catch (error) {
      console.error('Error:', error);
      Alert.alert('Error', 'No se pudo conectar con el servidor');
    }
  };

  const sendTestNotification = async () => {
    try {
      const response = await fetch(`${API_URL}/api/push/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: '🧪 Notificación de Prueba',
          body: '¡Funciona! Recibirás notificaciones cuando te escriban a WhatsApp',
        }),
      });

      if (response.ok) {
        Alert.alert('Enviada', 'Revisa tu notificación de prueba');
      }
    } catch (error) {
      Alert.alert('Error', 'No se pudo enviar la notificación de prueba');
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>🚤 HotBoat Notificaciones</Text>
      
      <View style={styles.card}>
        <Text style={styles.label}>Estado:</Text>
        <Text style={styles.value}>
          {expoPushToken ? '✅ Conectado' : '⏳ Conectando...'}
        </Text>
      </View>

      {expoPushToken && (
        <>
          <View style={styles.card}>
            <Text style={styles.label}>Token:</Text>
            <Text style={styles.tokenText} numberOfLines={1}>
              {expoPushToken}
            </Text>
          </View>

          <Button
            title="📨 Enviar Notificación de Prueba"
            onPress={sendTestNotification}
            color="#25D366"
          />
        </>
      )}

      <Text style={styles.info}>
        Recibirás una notificación cada vez que un cliente te escriba por WhatsApp 💬
      </Text>
    </View>
  );
}

async function registerForPushNotificationsAsync() {
  let token;

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('hotboat-messages', {
      name: 'Mensajes HotBoat',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#25D366',
    });
  }

  if (Device.isDevice) {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    
    if (finalStatus !== 'granted') {
      alert('¡Necesitas activar los permisos de notificaciones!');
      return;
    }
    
    token = (await Notifications.getExpoPushTokenAsync({
      projectId: Constants.expoConfig?.extra?.eas?.projectId ?? 'your-project-id',
    })).data;
    
    console.log('Push token:', token);
  } else {
    alert('Debes usar un dispositivo físico para recibir notificaciones');
  }

  return token;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f0f0f0',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 30,
    color: '#333',
  },
  card: {
    backgroundColor: 'white',
    padding: 15,
    borderRadius: 10,
    marginBottom: 15,
    width: '100%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  label: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#666',
    marginBottom: 5,
  },
  value: {
    fontSize: 18,
    color: '#25D366',
    fontWeight: 'bold',
  },
  tokenText: {
    fontSize: 10,
    color: '#999',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  info: {
    marginTop: 20,
    textAlign: 'center',
    color: '#666',
    paddingHorizontal: 20,
  },
});
```

---

## 🔧 Configuración

### 1. Cambiar la URL del servidor

En el código de la app, cambia:

```javascript
const API_URL = 'https://tu-app.up.railway.app';
```

Por la URL real de tu servidor Railway (ejemplo: `https://hotboat-whatsapp-production.up.railway.app`)

### 2. Ejecutar migración

```bash
railway run python run_migration_010.py
```

### 3. Probar notificaciones

1. Abre la app en tu celular
2. Espera a que se conecte (verás "✅ Conectado")
3. Presiona "Enviar Notificación de Prueba"
4. Deberías recibir una notificación

---

## 📨 Cómo Funcionan las Notificaciones

### Cuando alguien te escribe:

1. **Llega mensaje a WhatsApp** → webhook lo recibe
2. **Sistema envía notificación push** → tu celular la recibe
3. **Aparece notificación con**:
   - 💬 Nombre del contacto
   - 📝 Preview del mensaje
   - 🔔 Sonido y vibración

### Información en la notificación:

```
Título: 💬 Juan Pérez
Mensaje: Hola, quiero reservar para mañana...
```

---

## 🎨 Personalización

### Cambiar el canal de notificaciones (Android):

En el código, modifica:

```javascript
await Notifications.setNotificationChannelAsync('hotboat-messages', {
  name: 'Mensajes HotBoat',
  importance: Notifications.AndroidImportance.MAX,  // Máxima prioridad
  vibrationPattern: [0, 250, 250, 250],  // Patrón de vibración
  lightColor: '#25D366',  // Color LED (verde WhatsApp)
});
```

### Cambiar sonido de notificación:

```javascript
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,  // Activar/desactivar sonido
    shouldSetBadge: true,   // Mostrar badge en el ícono
  }),
});
```

---

## 🔍 Debugging

### Ver tokens registrados:

```sql
SELECT * FROM push_tokens ORDER BY last_used_at DESC;
```

### Probar notificación desde código:

```python
from app.notifications import push_notifier

await push_notifier.send_new_message_notification(
    contact_name="Juan Pérez",
    phone_number="56912345678",
    message_preview="Hola, quiero reservar..."
)
```

---

## 💰 Costos

- **Expo Push Notifications**: ✅ 100% GRATIS (sin límites)
- **Email anterior (Resend)**: ❌ $1 por cada 1000 emails

### Ahorro estimado:

Si recibes 100 mensajes/día:
- Email: ~$3/mes
- Push: **$0/mes** ✅

---

## 🆘 Troubleshooting

### "No recibo notificaciones"

1. Verifica que la app esté conectada (debe decir "✅ Conectado")
2. Revisa permisos de notificaciones en ajustes del teléfono
3. Prueba con el botón "Enviar Notificación de Prueba"
4. Verifica logs del servidor: `railway logs`

### "Error al registrar token"

1. Verifica que la URL del servidor esté correcta
2. Asegúrate de haber ejecutado la migración
3. Revisa que el servidor esté en línea

### "Token expirado"

Los tokens se limpian automáticamente si no se usan en 30 días. Solo abre la app de nuevo para re-registrar.

---

## 📚 Referencias

- Expo Push Notifications: https://docs.expo.dev/push-notifications/overview/
- Expo Snack: https://snack.expo.dev/
- Expo Go App: https://expo.dev/client

---

## 🎉 ¡Listo!

Ahora recibirás notificaciones push gratuitas cada vez que alguien te escriba por WhatsApp. ¡Adiós costos de email! 🚀
