#!/bin/bash
# Deploy Bot 2 a Prefect
# Uso: ./deploy_bot2_to_prefect.sh

echo "🚀 Deploying Bot 2 to Prefect..."

# Verificar que Prefect esté instalado
if ! command -v prefect &> /dev/null; then
    echo "❌ Prefect no está instalado"
    echo "   Instalar: pip install prefect==3.7.5"
    exit 1
fi

echo "✓ Prefect $(prefect version) detectado"

# Crear deployment
echo ""
echo "📦 Creando deployment..."
prefect deployment build bot2_executor.py:execute_bot2 \
    --name "bot2-test" \
    --description "Bot 2 - Reconciliación Softland vs Cartola (TEST)" \
    --tag "bot2" \
    --tag "reconciliacion" \
    --tag "test" \
    --output "bot2_deployment.yaml" \
    --overwrite

if [ $? -ne 0 ]; then
    echo "❌ Error creando deployment"
    exit 1
fi

echo "✓ Deployment creado: bot2_deployment.yaml"

# Desplegar
echo ""
echo "🚀 Desplegando..."
prefect deployment apply bot2_deployment.yaml

if [ $? -ne 0 ]; then
    echo "❌ Error desplegando"
    exit 1
fi

echo ""
echo "✅ Deployment exitoso!"
echo ""
echo "📌 Para ejecutar Bot 2 en Prefect:"
echo "   prefect deployment run 'execute_bot2/bot2-test'"
echo ""
echo "📌 Para ver logs:"
echo "   prefect flow-run ls"
echo ""
echo "📌 Para ver detalles en UI:"
echo "   prefect cloud login"
echo "   Luego abrir: https://app.prefect.cloud"
